#!/usr/bin/python
#   Copyright 2008 Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import sys
import os
import re
import pickle
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.sqs.connection import SQSConnection
from boto.sqs.message import Message
from boto.exception import *
from condorutils import SUCCESS, FAILURE
from condorutils.osutil import grep
from condorutils.readconfig import *
from condorec2e.sqs import *
from condorec2e.region import *

def main(argv=None):
   if argv == None:
      argv = sys.argv

   bucket = ''
   key = ''
   queue_name = ''
   region = ''
   ret_val = SUCCESS

   # Read the class ad from stdin and store the S3 information
   for line in sys.stdin:
      match = grep('^([^=]*)\s*=\s*(.*)$', line.strip())
      if match != None and match[0] != None and match[1] != None:
         attribute = match[0].strip().lower()
         val_match = grep('^"(.*)"$', match[1].strip())
         if val_match != None and val_match[0] != None:
            value = val_match[0].strip()
         else:
            value = match[1].strip()
         if attribute == 's3bucketid':
            bucket = value
            continue
         if attribute == 's3keyid':
            key = value
            continue
         if attribute == 'amazonaccesskey':
            aws_key = value
            continue
         if attribute == 'amazonsecretkey':
            aws_secret = value
            continue
         if attribute == 'amazonfullsqsqueuename':
            queue_name = value
            continue
         if attribute == 'ec2region':
            region = value


   # Pull the specific keys out of the files
   if os.path.exists(aws_key) == False or \
      os.path.exists(aws_secret) == False:
      sys.stderr.write('Error: Unable to read AWS key files')
      return(FAILURE)
   else:
      key_file = open(aws_key, 'r')
      aws_key_val = key_file.readlines()[0].strip()
      key_file.close()
      key_file = open(aws_secret, 'r')
      aws_secret_val = key_file.readlines()[0].strip()
      key_file.close()

   # Remove messages from SQS
   work_queue = None
   results_queue = None
   full_queue_name = '%s-%s' % (str(aws_key_val), queue_name)
   try:
      r_obj = AWSRegion.get_sqs_region(region)
      sqs_con = SQSConnection(aws_key_val, aws_secret_val, region=r_obj)
   except BotoServerError, error:
      sys.stderr.write('Error: Unable to connect to SQS: %s, %s\n' % (error.reason, error.body))
      return(FAILURE)

   # For some reason get_queue don't always return the queue even if it
   # exists, so must iterate over the existing queues and find it that
   # way.  Annoying.
   try:
      all_queues = sqs_con.get_all_queues()
   except BotoServerError, error:
      sys.stderr.write('Error: Unable to retrieve SQS queues: %s, %s\n'% (sqs_queue_name, error.reason, error.body))
      return(FAILURE)

   for q in all_queues: 
      if q.id.split('/')[2] == full_queue_name:
         work_queue = q
      if q.id.split('/')[2] == '%s-status' % full_queue_name:
         results_queue = q

   for queue in (work_queue, results_queue):
      if queue != None:
         # Remove all messages in the queue
         try:
            q_msg = queue.read()
         except SQSError, error:
            sys.stderr.write('Error reading messages from SQS queue "%s": %s, %s\n' % (q.id, error.reason, error.body))
            return(FAILURE)
         while q_msg != None:
            try:
               msg = pickle.loads(q_msg.get_body())
            except:
               # Likely bad message in the queue so remove it and continue
               # removing messages
               queue.delete_message(q_msg)
               try:
                  q_msg = queue.read()
               except SQSError, error:
                  sys.stderr.write('Error reading messages from SQS queue "%s": %s, %s\n' % (q.id, error.reason, error.body))
                  return(FAILURE)
               continue
   
            # Grab the S3 bucket if it wasn't in the input classad
            if bucket == '':
               try:
                  bucket = q_msg.s3_bucket
               except:
                  # Message had no s3_bucket for some reason.
                  sys.stderr.write('Error: Message has no S3 bucket\n')
                  return(FAILURE)
   
            # Grab the S3 key if it wasn't defined already
            if key == '':
               if msg.s3_key == None:
                  s3_key = grep('^S3KeyID\s*=\s*"(.+)"$', msg.class_ad)
                  if s3_key == None or s3_key[0] == None:
                     s3_key = grep('^s3keyid\s*=\s*"(.+)"$', msg.class_ad)
                  if s3_key != None and s3_key[0] != None:
                     key = s3_key[0]
               else:
                  key = msg.s3_key
   
            # Delete the message.  There may be more so keep processing
            queue.delete_message(q_msg)
   
            q_msg = queue.read()

   # Access S3
   try:
      s3_con = S3Connection(aws_key_val, aws_secret_val)
      s3_bucket_obj = s3_con.get_bucket(bucket)
   except BotoServerError, error:
      if grep('Not Found', error.reason) == None:
         sys.stderr.write('Error accessing S3 bucket "%s": %s, %s\n' % (bucket, error.reason, error.body))
         return(FAILURE)

   # Remove the data from S3, if there is any
   if key != '' and ret_val == SUCCESS:
      if s3_bucket_obj == None:
         sys.stderr.write('Error: Unable to access S3 to clean up data in S3 bucket %s\n' % bucket)
         return(FAILURE)
      else:
         try:
            s3_key_obj = s3_bucket_obj.get_key(key)
            if s3_key_obj != None:
               s3_bucket_obj.delete_key(s3_key_obj)
         except S3ResponseError, error:
            sys.stderr.write('Error: Unable to delete S3 key "%s": %s, %s\n' % (key, error.reason, error.body))
            return(FAILURE)

   # Remove the SQS queues.  If unable to do so, messages still exist in the
   # queues so cleanup will need to happen again
   if work_queue != None:
      try:
         sqs_con.delete_queue(work_queue)
      except BotoServerError, error:
         sys.stderr.write('Error: Unable to remove work SQS queue: %s, %s\n' % (error.reason, error.body))
         ret_val = FAILURE

   if results_queue != None:
      try:
         sqs_con.delete_queue(results_queue)
      except BotoServerError, error:
         sys.stderr.write('Error: Unable to remove status SQS queue: %s, %s\n' % (error.reason, error.body))
         ret_val = FAILURE

   return(ret_val)

if __name__ == '__main__':
   sys.exit(main())

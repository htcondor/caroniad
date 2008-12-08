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
import syslog
import re
import random
import pickle
import time
import tarfile
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.sqs.connection import SQSConnection
from boto.sqs.message import Message
from boto.exception import *
from jobhooks.functions import *
from ec2enhanced.functions import *

def main(argv=None):
   if argv == None:
      argv = sys.argv

   # Open a connection to the system logger
   syslog.openlog(os.path.basename(argv[0]))

   sqs_msg_id = ''
   bucket = ''
   key = ''
   key_file = ''
   ret_val = FAILURE
   status = 1
   state = ''

   # Read the class ad from stdin and store the S3 information
   for line in sys.stdin:
      match = grep('^(.*)\s*=\s*(.*)$', line.lstrip())
      if match != None and match[0] != None and match[1] != None:
         attribute = match[0].rstrip()
         val_match = grep('^"(.*)"$', match[1].rstrip())
         if val_match != None and val_match[0] != None:
            value = val_match[0].rstrip().lstrip()
         else:
            value = match[1].rstrip().lstrip()
      if attribute.lower() == 's3bucketid':
         bucket = value
         continue
      if attribute.lower() == 's3keyid':
         key = value
         continue
      if attribute.lower() == 'sqsmessageid':
         sqs_msg_id = value
         continue
      if attribute.lower() == 'amazonaccesskey':
         aws_key = value
         continue
      if attribute.lower() == 'amazonsecretkey':
         aws_secret = value
         continue
      if attribute.lower() == 'amazonsqsqueuename':
         queue_name = value
         continue
      if attribute.lower() == 'jobstate':
         state = value
         continue
      if attribute.lower() == 'jobstatus':
         status = value
         continue
      if attribute.lower() == 'amazonuserdatafile':
         key_file = value
         continue

   # Delete the file containing the encrypted keys if present
   if key_file != '' and os.path.exists(key_file):
      os.remove(key_file)

   # If the job completed, no need to clean up AWS
   if state == 'Exited' or status == 4:
      ret_val = SUCCESS
   else:
      # Pull the specific keys out of the files
      key_file = open(aws_key, 'r')
      aws_key_val = key_file.readlines()[0].rstrip()
      key_file.close()
      key_file = open(aws_secret, 'r')
      aws_secret_val = key_file.readlines()[0].rstrip()
      key_file.close()

      # Remove the work from SQS
      work_queue = None
      results_queue = None
      sqs_con = SQSConnection(aws_key_val, aws_secret_val)
      try:
         work_queue = sqs_con.create_queue('%s-%s' % (str(aws_key_val), queue_name))
      except BotoServerError, error:
         syslog.syslog(syslog.LOG_ERR, 'Error: %s, %s' % (error.reason, error.body))
         return(FAILURE)

      try:
         results_queue = sqs_con.create_queue('%s-%s' % (str(aws_key_val), 'condor_status_queue'))
      except:
         pass

      # Look for the job in the work queue, meaning it hasn't been processed yet
      q_msg = work_queue.read(60)
      msg_list = {}
      while q_msg != None:
         if sqs_msg_id.upper() == q_msg.id:
            work_queue.delete_message(q_msg)
            ret_val = SUCCESS
            break
         else:
            msg_list.update({q_msg.id:q_msg})
         q_msg = work_queue.read(60)

      # Reset the visibility timeouts on the messages not removed so they can be
      # read again by another processes
      for msg_key in msg_list.keys():
         msg_list[msg_key].change_visibility(1)
         del msg_list[msg_key]

      # Check the results queue to see if there are any status messages
      # or notification of job completion
      if results_queue != None:
         q_msg = results_queue.read(60)
         while q_msg != None:
            try:
               msg = pickle.loads(q_msg.get_body())
            except:
               # Likely bad message in the queue so skip it by setting the
               # visibility timer far enough in the future that we're unlikely
               # to hit it again this pass but not so far that it won't be seen
               # for a long time and then move on to the next message
               q_msg.change_visibility(15)
               continue

            matches = grep('^SQSMessageId\s*=\s*"(.*)"$', msg.class_ad)
            if matches != None:
               if sqs_msg_id.lower() == matches[0].lower():
                  # Found a message in the queue, which is good.  There may be
                  # more so keep processing
                  ret_val = SUCCESS
                  results_queue.delete_message(q_msg)
   
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
   
                  # Check the job status to see if this message notifies of
                  # job completion
#                  job_status = grep('^JobStatus\s*=\s*(.)$', msg.class_ad)
#                  if job_status != None and job_status[0] != None and \
#                     int(job_status[0].rstrip().lstrip()) == 4:
#                     ret_val = SUCCESS
               else:
                  msg_list.update({matches[0]:q_msg})
            q_msg = results_queue.read(60)

      # Reset the visibility timeouts on the messages not removed so they can be
      # read again by another processes
      for msg_key in msg_list.keys():
         msg_list[msg_key].change_visibility(1)
         del msg_list[msg_key]

      # Access S3
      if bucket != '':
         try:
            s3_con = S3Connection(aws_key_val, aws_secret_val)
            s3_bucket_obj = s3_con.create_bucket(bucket)
         except BotoServerError, error:
            syslog.syslog(syslog.LOG_ERR, 'Error: %s, %s' % (error.reason, error.body))
      else:
         syslog.syslog(syslog.LOG_INFO, 'No S3 bucket defined')

      # Remove the data from S3
      if key != '':
         try:
            s3_key_obj = s3_bucket_obj.get_key(key.upper())
            s3_bucket_obj.delete_key(s3_key_obj)
         except BotoServerError, error:
            syslog.syslog(syslog.LOG_ERR, 'Unable to delete S3 key "%s": %s, %s' % (key, error.reason, error.body))
            return(FAILURE)

      if bucket != '':
         try:
            s3_con.delete_bucket(s3_bucket_obj)
         except BotoServerError, error:
            syslog.syslog(syslog.LOG_INFO, 'Unable to delete S3 bucket "%s": %s, %s' % (bucket, error.reason, error.body))
            pass

   return(ret_val)

if __name__ == '__main__':
   sys.exit(main())

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
from subprocess import *
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
   file = open('/home/rsquared/condor/installation/cleanup.out', 'w')
   for line in sys.stdin:
      file.write(line)
      match = grep('^s3bucketid\s*=\s*"(.+)"$', line.lower())
      if match != None and match[0] != None:
         bucket = match[0].rstrip()
         continue
      match = grep('^s3keyid\s*=\s*"(.+)"$', line.lower())
      if match != None and match[0] != None:
         key = match[0].rstrip().upper()
         continue
      match = grep('^sqsmessageid\s*=\s*"(.+)"$', line.lower())
      if match != None and match[0] != None:
         sqs_msg_id = match[0].rstrip().upper()
         continue
      match = grep('^amazonaccesskey\s*=\s*"(.+)"$', line.lower())
      if match != None and match[0] != None:
         aws_key = match[0].rstrip()
         continue
      match = grep('^amazonsecretkey\s*=\s*"(.+)"$', line.lower())
      if match != None and match[0] != None:
         aws_secret = match[0].rstrip()
         continue
      match = grep('^amazonsqsqueuename\s*=\s*"(.+)"', line.lower())
      if match != None and match[0] != None:
         queue_name = match[0].rstrip()
         continue
      match = grep('^jobstate\s*=\s*"(.+)"$', line.lower())
      if match != None and match[0] != None:
         state = match[0].rstrip()
         continue
      match = grep('^jobstatus\s*=\s*(.+)$', line.lower())
      if match != None and match[0] != None:
         status = int(match[0].rstrip())
         continue
      match = grep('^amazonuserdatafile\s*=\s*"(.*)"$', line.lower())
      if match != None and match[0] != None:
         key_file = match[0].rstrip()
   file.close()

   # Delete the file containing the encrypted keys if present
   if key_file != '' and os.path.exists(key_file):
      os.remove(key_file)

   # If the job completed, no need to clean up AWS
   if state == 'exited' or status == 4:
      ret_val = SUCCESS
   else:
      # Pull the specific keys out of the files
      process = Popen(['cat', aws_key], stdout=PIPE)
      aws_key_val = process.communicate()[0].rstrip()
      process = Popen(['cat', aws_secret], stdout=PIPE)
      aws_secret_val = process.communicate()[0].rstrip()

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
            msg = pickle.loads(q_msg.get_body())
            matches = grep('^SQSMessageId\s*=\s*"(.*)"$', msg.class_ad)
            if matches != None:
               if sqs_msg_id.lower() == matches[0].lower():
                  results_queue.delete_message(q_msg)
   
                  # Grab the S3 key if it wasn't defined already
                  if key == '':
                     if msg.s3_key == None:
                        s3_key = grep('^s3keyid\s*=\s*"(.+)"$', msg.class_ad.lower())
                        if s3_key != None and s3_key[0] != None:
                           key = s3_key[0]
                     else:
                        key = msg.s3_key
   
                  # Check the job status to see if this message notifies of
                  # job completion
                  job_status = grep('^JobStatus\s*=\s*(.)$', msg.class_ad)
                  if job_status != None and job_status[0] != None and \
                     int(job_status[0].rstrip()) == 4:
                     ret_val = SUCCESS
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
         except:
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

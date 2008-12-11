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
import pickle
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.sqs.connection import SQSConnection
from jobhooks.functions import *
from ec2enhanced.functions import *

def main(argv=None):
   if argv == None:
      argv = sys.argv

   sqs_data = SQSEntry()
   sqs_msg_id = None
   request_classad = ''
   status_classad = ''
   aws_key = ''
   aws_secret = ''
   current_job_status = 1

   for line in sys.stdin:
      request_classad += line
      match = grep('^(.*)\s*=\s*"(.*)"$', line.lstrip())
      if match != None and match[0] != None and match[1] != None:
         attribute = match[0].rstrip().lstrip()
         value = match[1].rstrip().lstrip()
      if attribute.lower() == 'sqsmessageid':
         sqs_msg_id = value
         continue
      if attribute.lower() == 'amazonaccesskey':
         aws_key = value
         continue
      if attribute.lower() == 'amazonsecretkey':
         aws_secret = value
         continue
      if attribute.lower() == 'jobstatus':
         current_job_status = value
         continue
      if attribute.lower() == 'amazonfullsqsqueuename':
         queue_name = value
         continue

   # Get the specified Amazon key information
   if os.path.exists(aws_key) == False or os.path.exists(aws_secret) == False:
      syslog.syslog(syslog.LOG_ERR, 'Error: Unable to read AWS key files')
      sys.stderr.write('Error: Unable to read AWS key files')
      return(FAILURE)
   else:
      key_file = open(aws_key, 'r')
      aws_key_val = key_file.readlines()[0].rstrip()
      key_file.close()
      key_file = open(aws_secret, 'r')
      aws_secret_val = key_file.readlines()[0].rstrip()
      key_file.close()

   # Cycle through the results looking for info on the supplied class ad
   try:
      sqs_con = SQSConnection(aws_key_val, aws_secret_val)
   except:
      syslog.syslog(syslog.LOG_ERR, 'Error: Unable to connect to SQS')
      sys.stderr.write('Error: Unable to connect to SQS\n')
      return(FAILURE)
      
   sqs_queue_name = '%s-%s-status' % (str(aws_key_val), queue_name)
   try:
      sqs_queue = sqs_con.create_queue(sqs_queue_name)
      q_msg = sqs_queue.read(60)
   except:
      syslog.syslog(syslog.LOG_ERR, 'Error: Unable to access SQS queue "%s"' % sqs_queue_name)
      sys.stderr.write('Error: Unable to access SQS queue "%s"\n' % sqs_queue_name)
      return(FAILURE)

   job_complete_found = 0
   msg_list = {}
   while q_msg != None:
      try:
         msg = pickle.loads(q_msg.get_body())
      except:
         # Likely bad message in the queue so skip it by setting the
         # visibility timer far enough in the future that we're unlikely
         # to hit it again this pass but not so far that it won't be seen
         # for a long time and then move on to the next message
         q_msg.change_visibility(15)
         q_msg = sqs_queue.read(60)
         continue

      matches = grep('^SQSMessageId\s*=\s*"(.+)"$', msg.class_ad)
      if matches != None:
         if sqs_msg_id.lower() == matches[0].lower():
            # This message will be the status update unless a message
            # indicating job completion has already been found or the job
            # requesting an update has already been marked as completed (4)
            if job_complete_found == 0 and current_job_status != 4:
               # We haven't found a message to indicate the job is done
               # so this message will be the status update
               status_classad = msg.class_ad
               s3_key = msg.s3_key

               # Add the S3 Key ID if it isn't there already.  This happens
               # in the case where nothing was needed to be transfered to
               # the execute node
               key = grep('^S3KeyID\s*=.*$', status_classad)
               if s3_key != None and key == None:
                  status_classad += 'S3KeyID = "%s"\n' % s3_key

               # Remove the key data if it exists
               key_file = grep('^AmazonUserDataFile\s*=\s*"(.*)"$', request_classad)
               if key_file != None and key_file[0] != None and \
                  os.path.exists(key_file[0].rstrip()):
                  os.remove(key_file[0].rstrip())

               # Check the job status to see if this message notifies of
               # job completion
               job_status = grep('^JobStatus\s*=\s*(.)$', status_classad)
               if job_status != None and job_status[0] != None and \
                  int(job_status[0].rstrip()) == 4:
                  # We found an update that indicates the job completed.
                  # Need to set the flag indicating the job is complete so
                  # any remaining status update messages will be removed from
                  # the queue.  This is necessary because SQS isn't guaranteed
                  # to be FIFO, even though it tries to be so
                  job_complete_found = 1

            # Remove the message from the queue
            sqs_queue.delete_message(q_msg)
            if job_complete_found == 0:
               # Message we found wasn't a job complete update, so break
               # out of the loop because we only want to continue processing
               # status messages if we received a message that indicates the
               # job completed
               break
         else:
            msg_list.update({matches[0]:q_msg})
      q_msg = sqs_queue.read(60)

   # Reset the visibility timeouts on the status messages so they can be
   # read again by another process
   for key in msg_list.keys():
      try:
         msg_list[key].change_visibility(1)
      except:
         pass
      del msg_list[key]

   # Print the class ad containing updated information if it was found
   if status_classad != '':
      print status_classad

   return(SUCCESS)

if __name__ == '__main__':
   sys.exit(main())

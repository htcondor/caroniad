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
import time
from subprocess import *
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

   file = open('/home/rsquared/condor/installation/status.out', 'w')
   for line in sys.stdin:
      file.write(line)
      request_classad += line
      match = re.match('^sqsmessageid\s*=\s*"(.+)"$', line.lower())
      if match != None and match.groups() != None:
         sqs_msg_id = match.groups()[0].rstrip()
         continue
      match = re.match('^amazonaccesskey\s*=\s*"(.+)"$', line.lower())
      if match != None and match.groups() != None:
         aws_key = match.groups()[0].rstrip()
         continue
      match = re.match('^amazonsecretkey\s*=\s*"(.+)"$', line.lower())
      if match != None and match.groups() != None:
         aws_secret = match.groups()[0].rstrip()
         continue

   file.close()

   # Get the specified Amazon key information
   process = Popen(['cat', aws_key], stdout=PIPE)
   aws_key_val = process.communicate()[0].rstrip()
   process = Popen(['cat', aws_secret], stdout=PIPE)
   aws_secret_val = process.communicate()[0].rstrip()

   # Cycle through the results looking for info on the supplied class ad
   sqs_con = SQSConnection(aws_key_val, aws_secret_val)
   sqs_queue_name = '%s-%s' % (str(aws_key_val), 'condor_status_queue')
   sqs_queue = sqs_con.create_queue(sqs_queue_name)
   job_complete_found = 0
   q_msg = sqs_queue.read(60)
   msg_list = {}
   while q_msg != None:
      msg = pickle.loads(q_msg.get_body())
      matches = grep('^SQSMessageId\s*=\s*"(.+)"$', msg.class_ad)
      if matches != None:
         if sqs_msg_id.lower() == matches[0].lower():
            if job_complete_found == 0:
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

#               job_iwd = grep('^Iwd\s*=\s*(.*)$', status_classad)
#               if job_iwd != None and job_iwd[0] != None:
#                  syslog.syslog(syslog.LOG_INFO, job_iwd[0])

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
            sqs_queue.delete_message(q_msg)
            if job_complete_found == 0:
               # Message we found wasn't a job complete update, so break
               # out of the loop
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

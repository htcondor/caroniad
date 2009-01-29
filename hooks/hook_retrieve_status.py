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

   status_classad = ''
   aws_key = ''
   aws_secret = ''
   queue_name = ''
   update_classad = ''
   job_completed = 'FALSE'
   update_skip_attribs = ['jobstatus', 'imagesize', 'enteredcurrentstatus',
                          'jobstartdate']
   attempts = 0

   for line in sys.stdin:
      match = grep('^([^=]*)\s*=\s*(.*)$', line.lstrip())
      if match != None and match[0] != None and match[1] != None:
         attribute = match[0].rstrip().lstrip()
         val_match = grep('^"(.*)"$', match[1].rstrip())
         if val_match != None and val_match[0] != None:
            value = val_match[0].rstrip().lstrip()
         else:
            value = match[1].rstrip().lstrip()
         if attribute.lower() == 'amazonaccesskey':
            aws_key = value
            continue
         if attribute.lower() == 'amazonsecretkey':
            aws_secret = value
            continue
         if attribute.lower() == 'ec2jobsuccessful':
            job_completed = value
            continue
         if attribute.lower() == 'amazonfullsqsqueuename':
            queue_name = value
            continue
         if attribute.lower() == 'ec2runattempts':
            attempts = int(value)

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

   # Look for an update
   try:
      sqs_con = SQSConnection(aws_key_val, aws_secret_val)
   except:
      syslog.syslog(syslog.LOG_ERR, 'Error: Unable to connect to SQS')
      sys.stderr.write('Error: Unable to connect to SQS\n')
      return(FAILURE)
      
   sqs_queue_name = '%s-%s-status' % (str(aws_key_val), queue_name)
   try:
      sqs_queue = sqs_con.get_queue(sqs_queue_name)
   except BotoServerError, error:
      syslog.syslog(syslog.LOG_ERR, 'Error: Unable to retrieve SQS queue "%s": %s, %s'% (sqs_queue_name, error.reason, error.body))
      sys.stderr.write('Error: Unable to retrieve SQS queue "%s": %s, %s\n'% (sqs_queue_name, error.reason, error.body))
      return(FAILURE)

   if sqs_queue != None and job_completed.lower() != 'true':
      q_msg = sqs_queue.read(5)
      while q_msg != None:
         try:
            msg = pickle.loads(q_msg.get_body())
            break
         except:
            # Likely bad message in the queue so skip it by setting the
            # visibility timer far enough in the future that we're unlikely
            # to hit it again this pass but not so far that it won't be seen
            # for a long time, and then move on to the next message
            q_msg.change_visibility(15)
            q_msg = sqs_queue.read(5)
            continue

      if q_msg != None:
         # This message will be the status update
         status_classad = msg.class_ad
         s3_key = msg.s3_key

         # Add the S3 Key ID if it isn't there already.  This happens
         # in the case where nothing was needed to be transfered to
         # the execute node
         key = grep('^S3KeyID\s*=.*$', status_classad)
         if s3_key != None and key == None:
            status_classad += 'S3KeyID = "%s"\n' % s3_key

         # If the message notifies of a run attempt, increment the counter
         # on the number of runs attempts
         run_try = grep ('^EC2JobAttempted\s*=\s*(.*)$', status_classad)
         if run_try != None and run_try[0] != None and \
            run_try[0].rstrip().lower() == 'true':
            update_classad += 'EC2RunAttempts = %d\n' % (attempts+1)

         # Check the job status to see if this message notifies of
         # job completion
         job_status = grep('^JobStatus\s*=\s*(.)$', status_classad)
         if job_status != None and job_status[0] != None and \
            int(job_status[0].rstrip()) == 4:
            # We found an update that indicates the job completed.
            # Add a marker to the classad saying the job has completed.
            update_classad += 'EC2JobSuccessful = True\n'
         else:
            # Remove the message from the queue only if it's not the success
            # message
            sqs_queue.delete_message(q_msg)

         # Print the update information
         if update_classad != '':
            print update_classad

   return(SUCCESS)

if __name__ == '__main__':
   sys.exit(main())

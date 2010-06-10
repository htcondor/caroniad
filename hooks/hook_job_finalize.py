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
import logging
import tempfile
import time
import pickle
import shutil
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.sqs.connection import SQSConnection
from boto.exception import *
from condorutils import SUCCESS, FAILURE
from condorutils.log import *
from condorutils.osutil import grep, tarball_extract
from condorutils.readconfig import *
from condorec2e.sqs import *

def remove_dir(dir):
   if dir[-1] == os.sep:
      dir = dir[:-1]
   files = os.listdir(dir)
   for file in files:
      if file == '.' or file == '..':
         continue
      path = dir + os.sep + file
      if os.path.isdir(path):
         remove_dir(path)
      else:
         os.remove(path)
   os.rmdir(dir)

def main(argv=None):
   if argv == None:
      argv = sys.argv

   aws_key = ''
   aws_secret = ''
   s3_bucket_obj = ''
   stdout = ''
   stderr = ''
   remaps = ''
   ec2_success = "false"
   ret_val = SUCCESS
   cluster = 0
   proc = 0
   done_classad = ''
   s3_key = ''
   log_name = os.path.basename(argv[0])

   # Configure the logging system
   try:
      file = read_condor_config('EC2E_HOOK', ['LOG'])
   except ConfigError, error:
      sys.stderr.write('Error: %s.  Exiting' % error.msg)
      return(FAILURE)

   try:
      size = int(read_condor_config('MAX_EC2E_HOOK', ['LOG'])['log'])
   except:
      size = 1000000

   base_logger = create_file_logger(log_name, '%s.finalize' % file['log'], logging.INFO, size=size)

   log(logging.INFO, log_name, 'Hook running')

   # Read the source class ad from stdin and store it as well as the
   # job status.  The end of the source job is noted by '------'
   for line in sys.stdin:
      if line.rstrip() == '------':
         break
      match = grep('^([^=]*)\s+=\s+(.*)$', line.lstrip())
      if match != None and match[0] != None and match[1] != None:
         attribute = match[0].rstrip()
         val_match = grep('^"(.*)"$', match[1].rstrip())
         if val_match != None and val_match[0] != None:
            value = val_match[0].rstrip().lstrip()
         else:
            value = match[1].rstrip().lstrip()
         if attribute.lower() == 'iwd':
            iwd = value
            continue
         if attribute.lower() == 'transferoutputremaps':
            remaps = value
            continue
         if attribute.lower() == 'out' and value.lower() != '_condor_stdout':
            stdout = value
            continue
         if attribute.lower() == 'err' and value.lower() != '_condor_stderr':
            stderr = value
            continue
         if attribute.lower() == 'clusterid':
            cluster = value
            continue
         if attribute.lower() == 'procid':
            proc = value
            continue

   # Read the routed class ad from stdin and store the S3 information and
   # the job status
   for line in sys.stdin:
      match = grep('^([^=]*)\s*=\s*(.*)$', line.lstrip())
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
            s3_key = value
            continue
         if attribute.lower() == 'amazonaccesskey':
            aws_key = value
            continue
         if attribute.lower() == 'amazonsecretkey':
            aws_secret = value
            continue
         if attribute.lower() == 'ec2jobsuccessful':
            ec2_success = value
            continue
         if attribute.lower() == 'amazonfullsqsqueuename':
            queue_name = value
            continue

   # If the source job is not in the completed state, but the routed job is
   # then there was a failure running the AMI.  Exit with status 2 so the
   # job will be re-routed.
   if ec2_success.lower() == "false":
      log(logging.INFO, log_name, 'Job %d.%d did not complete.  Forcing the job to be routed again' % (int(cluster), int(proc)))
      sys.stderr.write('Job %d.%d did not complete.  Forcing the job to be routed again\n' % (int(cluster), int(proc)))
      return(FAILURE)

   # Pull the specific keys out of the files
   if os.path.exists(aws_key) == False or os.path.exists(aws_secret) == False:
      log(logging.ERROR, log_name, 'Unable to read AWS key files')
      sys.stderr.write('Error: Unable to read AWS key files')
      return(FAILURE)
   else:
      key_file = open(aws_key, 'r')
      aws_key_val = key_file.readlines()[0].rstrip()
      key_file.close()
      key_file = open(aws_secret, 'r')
      aws_secret_val = key_file.readlines()[0].rstrip()
      key_file.close()

   # Connect to S3
   failed = 1
   for attempt in range(1,5):
      try:
         s3_con = S3Connection(aws_key_val, aws_secret_val)
         s3_bucket_obj = s3_con.get_bucket(bucket)
         failed = 0
         break
      except BotoServerError, error:
         log(logging.ERROR, log_name, 'Error accessing S3: %s, %s' % (error.reason, error.body))
         sys.stderr.write('Error accessing S3: %s, %s\n' % (error.reason, error.body))
         time.sleep(5)
         pass

   if failed == 1:
      return(FAILURE)

   if s3_bucket_obj == None:
      log(logging.ERROR, log_name, 'Unable to access S3 to retrieve data from S3 bucket %s' % bucket)
      sys.stderr.write('Error: Unable to access S3 to retrieve data from S3 bucket %s\n' % bucket)
      return(FAILURE)
   else:
      s3_key_obj = s3_bucket_obj.get_key(s3_key)

   # Access S3 and extract the data into the staging area
   results_filename = 'results.tar.gz'
   try:
      temp_dir = tempfile.mkdtemp(suffix=str(os.getpid()))
      os.chdir(temp_dir)
   except:
      log(logging.ERROR, log_name, 'Unable to chdir to "%s"' % iwd)
      sys.stderr.write('Unable to chdir to "%s"\n' % iwd)
      if os.path.exists(temp_dir):
         os.removedirs(temp_dir)
      return(FAILURE)

   if s3_key_obj != None:
      s3_key_obj.get_contents_to_filename(results_filename)
   else:
      log(logging.ERROR, log_name, 'Unable to find S3 key "%s" in S3 bucket "%s"' % (s3_key, bucket))
      sys.stderr.write('Error: Unable to find S3 key "%s" in S3 bucket "%s"\n' % (s3_key, bucket))
      if os.path.exists(results_filename):
         os.remove(results_filename)
      os.chdir('/tmp')
      if os.path.exists(temp_dir):
         os.removedirs(temp_dir)
      return(FAILURE)

   try:
      tarball_extract(results_filename)
   except:
      log(logging.ERROR, log_name, 'Unable to extract results file')
      sys.stderr.write('Error: Unable to extract results file\n')
      os.remove(results_filename)
      os.chdir('/tmp')
      if os.path.exists(temp_dir):
         remove_dir(temp_dir)
      return(FAILURE)

   if os.path.exists(results_filename):
      os.remove(results_filename)

   # Place the extracted files in their proper locations, starting with the
   # remaps
   if remaps != '':
      for remap in remaps.split(';'):
         remap_info = remap.split('=')
         if os.path.exists(remap_info[0]) == True:
            os.rename(remap_info[0], remap_info[1])

   for file in os.listdir('.'):
      shutil.move(file, iwd)

   # Remove the data from S3
   if s3_bucket_obj != '':
      try:
         s3_bucket_obj.delete_key(s3_key_obj)
      except BotoServerError, error:
         log(logging.ERROR, log_name, 'Warning: Unable to delete S3 key.  Key should be deleted during cleanup: %s, %s' % (error.reason, error.body))
         sys.stderr.write('Warning: Unable to delete S3 key.  Key should be deleted during cleanup %s, %s\n' % (error.reason, error.body))

   # Remove the temporary directory
   try:
      os.chdir('/tmp')
      remove_dir(temp_dir)
   except:
      log(logging.ERROR, log_name, 'Warning: Failed to remove temporary directory "%s"' % temp_dir)
      sys.stderr.write('Warning: Failed to remove temporary directory "%s"\n' % temp_dir)

   # Access SQS to get the final stats of the of the job
   failed = 1
   for attempt in range(1,5):
      try:
         sqs_con = SQSConnection(aws_key_val, aws_secret_val)
         failed = 0
         break
      except BotoServerError, error:
         log(logging.ERROR, log_name, 'Unable to connect to SQS: %s, %s'% (error.reason, error.body))
         sys.stderr.write('Error: Unable to connect to SQS: %s, %s\n' % (error.reason, error.body))
         time.sleep(5)
         pass

   if failed == 1:
      return(FAILURE)

   # Retrieve the exit status message and print it as the update
   sqs_queue_name = '%s-%s-status' % (str(aws_key_val), queue_name)
   try:
      sqs_queue = sqs_con.get_queue(sqs_queue_name)
   except BotoServerError, error:
      log(logging.ERROR, log_name, 'Unable to retrieve SQS queue "%s": %s, %s' % (sqs_queue_name, error.reason, error.body))
      sys.stderr.write('Error: Unable to retrieve SQS queue "%s": %s, %s\n' % (sqs_queue_name, error.reason, error.body))
      return(FAILURE)
      
   # Find the completion message
   if sqs_queue != None:
      q_msg = sqs_queue.read(5)
      while q_msg != None:
         try:
            msg = pickle.loads(q_msg.get_body())
         except:
            # Likely bad message in the queue so skip it by setting the
            # visibility timer far enough in the future that we're unlikely
            # to hit it again this pass but not so far that it won't be seen
            # for a long time, and then move on to the next message
            q_msg.change_visibility(15)
            q_msg = sqs_queue.read(5)
            continue

         # Check the job status to see if this message notifies of
         # job completion
         job_status = grep('^JobStatus\s*=\s*(.)$', msg.class_ad)
         if job_status != None and job_status[0] != None and \
            int(job_status[0].rstrip()) == 4:
            # We found the update that indicates the job completed.  This
            # message is the update to the source job
            done_classad = msg.class_ad
            break
         else:
            q_msg = sqs_queue.read(5)

   if done_classad != '':
      print done_classad

   log(logging.INFO, log_name, 'Hook exited')
   return(SUCCESS)

if __name__ == '__main__':
   sys.exit(main())

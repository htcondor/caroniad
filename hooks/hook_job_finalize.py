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
import tempfile
import time
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.exception import *
from jobhooks.functions import *
from ec2enhanced.functions import *

def main(argv=None):
   if argv == None:
      argv = sys.argv

   # Open a connection to the system logger
   syslog.openlog(os.path.basename(argv[0]))

   aws_key = ''
   aws_secret = ''
   s3_bucket_obj = ''
   stdout = ''
   stderr = ''
   remaps = ''
   ec2_success = False
   ret_val = SUCCESS

   # Read the source class ad from stdin and store it as well as the
   # job status.  The end of the source job is noted by '------'
   for line in sys.stdin:
      if line.rstrip() == '------':
         break
      match = grep('^(.*)\s+=\s+(.*)$', line.lstrip())
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

   # Read the routed class ad from stdin and store the S3 information and
   # the job status
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
         if attribute.lower() == 'amazonaccesskey':
            aws_key = value
            continue
         if attribute.lower() == 'amazonsecretkey':
            aws_secret = value
            continue
         if attribute.lower() == 'ec2jobsuccessful':
            ec2_success = value
            continue

   # If the source job is not in the completed state, but the routed job is
   # then there was a failure running the AMI.  Exit with status 2 so the
   # job will be re-routed.
   if ec2_success == False:
      syslog.syslog(syslog.LOG_INFO, 'The job did not complete.  Forcing the job to be routed again')
      sys.stderr.write('The job did not complete.  Forcing the job to be routed again\n')
      return(FAILURE)

   # Pull the specific keys out of the files
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

   # Access S3 and extract the data into the staging area
   results_filename = 'results.tar.gz'
   temp_dir = tempfile.mkdtemp(suffix=str(os.getpid()))
   try:
      os.chdir(temp_dir)
   except:
      syslog.syslog(syslog.LOG_ERR, 'Unable to chdir to "%s"' % iwd)
      sys.stderr.write('Unable to chdir to "%s"\n' % iwd)
      os.removedirs(temp_dir)
      return(FAILURE)

   # Connect to S3
   failed = 1
   for attempt in range(1,5):
      try:
         s3_con = S3Connection(aws_key_val, aws_secret_val)
         s3_bucket_obj = s3_con.get_bucket(bucket)
         failed = 0
         break
      except BotoServerError, error:
         syslog.syslog(syslog.LOG_ERR, 'Error accessing S3: %s, %s' % (error.reason, error.body))
         sys.stderr.write('Error accessing S3: %s, %s\n' % (error.reason, error.body))
         time.sleep(5)
         pass

   if failed == 1:
      os.removedirs(temp_dir)
      return(FAILURE)

   if s3_bucket_obj == None:
      syslog.syslog(syslog.LOG_ERR, 'Error: Unable to access S3 to retrieve data from S3 bucket %s' % bucket)
      sys.stderr.write('Error: Unable to access S3 to retrieve data from S3 bucket %s\n' % bucket)
      os.removedirs(temp_dir)
      return(FAILURE)
   else:
      s3_key_obj = s3_bucket_obj.get_key(key)

   if s3_key_obj != None:
      s3_key_obj.get_contents_to_filename(results_filename)
   else:
      syslog.syslog(syslog.LOG_ERR, 'Error: Unable to find S3 key "%s" in S3 bucket "%s"' % (key, bucket))
      sys.stderr.write('Error: Unable to find S3 key "%s" in S3 bucket "%s"\n' % (key, bucket))
      os.removedirs(temp_dir)
      return(FAILURE)

   try:
      tarball_extract(results_filename)
   except:
      syslog.syslog(syslog.LOG_ERR, 'Error: Unable to extract results file')
      sys.stderr.write('Error: Unable to extract results file')
      os.removedirs(temp_dir)
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
      os.rename(file, '%s/%s' % (iwd, file))

   # Remove the data from S3
   if s3_bucket_obj != '':
      s3_bucket_obj.delete_key(s3_key_obj)

   # Remove the temporary directory
   os.removedirs(temp_dir)

   return(SUCCESS)

if __name__ == '__main__':
   sys.exit(main())

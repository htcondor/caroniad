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

   # Get the spool directory
   spool_dir = sys.argv[1]

   aws_key = ''
   aws_secret = ''
   s3_bucket_obj = ''

   # Read the class ad from stdin and store the S3 information
   for line in sys.stdin:
      match = grep('^(.*)\s*=\s*"(.*)"$', line.lstrip())
      if match != None and match[0] != None and match[1] != None:
         attribute = match[0].rstrip()
         value = match[1].rstrip()
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
   try:
      os.chdir(spool_dir)
   except:
      syslog.syslog(syslog.LOG_ERR, 'Unable to chdir to "%s"' % spool_dir)

   try:
      s3_con = S3Connection(aws_key_val, aws_secret_val)
      s3_bucket_obj = s3_con.get_bucket(bucket)
      if s3_bucket_obj == None:
         syslog.syslog(syslog.LOG_ERR, 'Error: Unable to access S3 to retrieve data from S3 bucket %s' % bucket)
         sys.stderr.write('Error: Unable to access S3 to retrieve data from S3 bucket %s\n' % bucket)
         return(FAILURE)
      else:
         s3_key_obj = s3_bucket_obj.get_key(key)

      if s3_key_obj != None:
         s3_key_obj.get_contents_to_filename(results_filename)
      else:
         syslog.syslog(syslog.LOG_ERR, 'Error: Unable to find S3 key "%s" in S3 bucket "%s"' % (key, bucket))
         sys.stderr.write('Error: Unable to find S3 key "%s" in S3 bucket "%s"\n' % (key, bucket))
         return(FAILURE)
   except BotoServerError, error:
      syslog.syslog(syslog.LOG_ERR, 'Error accessing S3: %s, %s' % (error.reason, error.body))
      sys.stderr.write('Error accessing S3: %s, %s\n' % (error.reason, error.body))
      return(FAILURE)
   tarball_extract(results_filename)
   if os.path.exists(results_filename):
      os.remove(results_filename)

   # Remove the data from S3
   if s3_bucket_obj != '':
      s3_bucket_obj.delete_key(s3_key_obj)

   return(SUCCESS)

if __name__ == '__main__':
   sys.exit(main())

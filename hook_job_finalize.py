#!/usr/bin/python

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
from aws_common import SQSEntry
from workfetch_common import *

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
   file = open('/home/rsquared/condor/installation/exit.out', 'w')
   for line in sys.stdin:
      file.write(line)
      match = grep('^s3bucketid\s*=\s*"(.*)"$', line.lower())
      if match != None and match[0] != None:
         bucket = match[0].rstrip()
         continue
      match = grep('^s3keyid\s*=\s*"(.*)"$', line.lower())
      if match != None and match[0] != None:
         key = match[0].rstrip()
         continue
      match = grep('^amazonaccesskey\s*=\s*"(.+)"$', line.lower())
      if match != None and match[0] != None:
         aws_key = match[0].rstrip()
         continue
      match = grep('^amazonsecretkey\s*=\s*"(.+)"$', line.lower())
      if match != None and match[0] != None:
         aws_secret = match[0].rstrip()
         continue

   file.close()

   # Pull the specific keys out of the files
   process = Popen(['cat', aws_key], stdout=PIPE)
   aws_key_val = process.communicate()[0].rstrip()
   process = Popen(['cat', aws_secret], stdout=PIPE)
   aws_secret_val = process.communicate()[0].rstrip()

   # Access S3 and extract the data into the staging area
   results_filename = 'results.tar.gz'
   try:
      os.chdir(spool_dir)
   except:
      syslog.syslog(syslog.LOG_ERR, "os.chdir error")

   try:
      s3_con = S3Connection(aws_key_val, aws_secret_val)
      s3_bucket_obj = s3_con.get_bucket(bucket)
      s3_key_obj = s3_bucket_obj.get_key(key.upper())
      if s3_key_obj != None:
         s3_key_obj.get_contents_to_filename(results_filename)
         tarball_extract(results_filename)
      else:
         syslog.syslog(syslog.LOG_ERR, 'Unable to find S3 key "%s" in S3 bucket "%s"' % (key, bucket))
         return(FAILURE)
   except BotoServerError, error:
      syslog.syslog(syslog.LOG_ERR, 'Error: %s, %s' % (error.reason, error.body))
   if os.path.exists(results_filename):
      os.remove(results_filename)

   # Remove the data from S3
   if s3_bucket_obj != '':
      s3_bucket_obj.delete_key(s3_key_obj)
      try:
         s3_con.delete_bucket(s3_bucket_obj)
      except:
         pass

   return(SUCCESS)

if __name__ == '__main__':
   sys.exit(main())

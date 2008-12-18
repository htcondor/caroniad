#!/usr/bin/python

# To use this tool, the environment must have AWS_ACCESS_KEY_ID set to the
# AWS access key and AWS_SECRET_ACCESS_KEY set to the secret access key.

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
from ec2enhanced.functions import SQSEntry
from jobhooks.functions import *

# Connect to S3 and delete all buckets except for ec2_enhanced
s3_con = S3Connection()
buckets = s3_con.get_all_buckets()
for bucket in buckets:
   print "Examining bucket: " + bucket.name
   if bucket.name == "xerox_beta" or bucket.name == 'ec2etesting':
      continue
   s3_bucket = s3_con.get_bucket(bucket.name)
   for s3_key in s3_bucket.list():
#      if re.match('^rhel5', s3_key.key) != None:
#         continue
      print "Erasing key " + s3_key.key
#      s3_key.get_contents_to_filename('contents-%s-%s.tar.gz' % (bucket.name,s3_key.key))
      s3_bucket.delete_key(s3_key)
   print "Erasing bucket " + bucket.name
   s3_con.delete_bucket(bucket)

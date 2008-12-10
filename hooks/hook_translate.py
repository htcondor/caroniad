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
import tarfile
import base64
from popen2 import popen2
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.sqs.connection import SQSConnection
from boto.sqs.message import Message
from jobhooks.functions import *
from ec2enhanced.functions import *

def main(argv=None):
   if argv == None:
      argv = sys.argv

   max_key_id = 1000000000
   sqs_data = SQSEntry()
   grid_classad = ''
   iwd = ''
   create_sandbox = 'no'
   transfer_exe = 'true'
   skip_attribs = ['clusterid', 'procid', 'bufferblocksize', 'buffersize',
                   'condorplatform', 'condorversion', 'coresize',
                   'globaljobid', 'qdate', 'remotewallclocktime', 'servertime',
                   'autoclusterid', 'autoclusterattrs', 'currenthosts']
   int_reset_attribs = ['exitstatus', 'completiondate', 'localsyscpu',
                        'localusercpu', 'numckpts', 'numrestarts',
                        'numsystemholds', 'committedtime', 'totalsuspensions',
                        'lastsuspensiontime','cumulativesuspensiontime']
   float_reset_attribs = ['remoteusercpu', 'remotesyscpu']
   transfer_attribs = ['cmd', 'command', 'in', 'transferinput']
   delim = '------'
   aws_key = ''
   aws_secret = ''
   aws_public_key = ''
   aws_private_key = ''
   bucket_id = ''
   queue_name = ''
   rsa_public_key = ''

   # Parse the route information from stdin.
   route = grep('^\[\s*(.*)\s*\]$', sys.stdin.readline())[0]
   for line in route.split(';'):
      match = grep('^(.*)\s*=\s*"(.*)"$', line.lstrip())
      if match != None and match[0] != None and match[1] != None:
         attribute = match[0].rstrip()
         value = match[1].rstrip()
         if attribute.lower() == 'set_amazonpublickey':
            aws_public_key = value
            continue
         if attribute.lower() == 'set_amazonprivatekey':
            aws_private_key = value
            continue
         if attribute.lower() == 'set_amazonaccesskey':
            aws_key = value
            continue
         if attribute.lower() == 'set_amazonsecretkey':
            aws_secret = value
            continue
         if attribute.lower() == 'set_amazons3bucketname':
            bucket_id = value
            continue
         if attribute.lower() == 'set_amazonsqsqueuename':
            queue_name = value
            continue
         if attribute.lower() == 'set_rsapublickey':
            rsa_public_key = value
            continue

   sqs_data.class_ad += 'AmazonSQSQueueName = "%s"\n' % queue_name

   # Read the original class ad from stdin and store it for submission
   # to SQS.  Additionally, convert it to an EC2 classad for output
   for line in sys.stdin:
      if line.rstrip() == delim:
         continue
      match = re.match('^(.*)\s*=\s*(.*)$', line)
      if match != None and match.groups() != None:
         attribute = match.groups()[0].rstrip()
         value = match.groups()[1].rstrip()
         if attribute.lower() == 'iwd':
            # Remove the IWD from the class ad so the execute directory
            # will be used
            iwd = value.rstrip()
         if attribute.lower() == 'amazonpublickey':
            if aws_public_key == '':
               user_aws_public_key = grep('^"(.*)"$', value)[0]
            continue
         if attribute.lower() == 'amazonprivatekey':
            if aws_private_key == '':
               user_aws_private_key = grep('^"(.*)"$', value)[0]
            continue
         if attribute.lower() == 'amazonaccesskey':
            if aws_key == '':
               user_aws_key = grep('^"(.*)"$', value)[0]
            continue
         if attribute.lower() == 'amazonsecretkey':
            if aws_secret == '':
               user_aws_secret = grep('^"(.*)"$', value)[0]
            continue
         if attribute.lower() == 'rsapublickey':
            if rsa_public_key == '':
               user_rsa_public_key = grep('^"(.*)"$', value)[0]
            continue
         if attribute.lower() in skip_attribs:
            continue
         sqs_data.class_ad += str(line)

         if attribute.lower() == 'jobuniverse':
            grid_classad += 'JobUniverse = 9\n'
            grid_classad += 'Remote_JobUniverse = ' + str(value) + '\n'
            continue
         if attribute.lower() in int_reset_attribs:
            grid_classad += attribute + ' = 0\n'
            continue
         if attribute.lower() in float_reset_attribs:
            grid_classad += attribute + ' = 0.0\n'
            continue
         if attribute.lower() == 'jobstatus':
            grid_classad += attribute + ' = 1\n'
            continue
         if attribute.lower() == 'exitbysignal':
            grid_classad += attribute + ' = FALSE\n'
            continue
         if attribute.lower() == 'shouldtransferfiles':
            create_sandbox = re.match('^"(.+)"$', value.lower()).groups()[0]
            grid_classad += attribute + ' = "NO"\n'
            continue
         if attribute.lower() == 'transferexecutable':
            transfer_exe = value.lower()
         if attribute.lower() == 'cmd' or attribute.lower() == 'command':
            executable = value
      grid_classad += str(line)

   # Search through the class ad and make modifications to the files/paths
   # as necessary
   new_ad = ''
   files = []
   for line in sqs_data.class_ad.split('\n'):
      match = re.match('^(.*)\s*=\s*(.*)$', line)
      if match != None and match.groups() != None:
         attribute = match.groups()[0].rstrip()
         value = match.groups()[1].rstrip()

         # Ignore files in /dev (like /dev/null)
         if re.match('^"/dev/.*"', value) != None:
            continue

         # Remove quotes if they exist.  This is a string, so try to split on
         # the '/' character.  If a / exists, it's a file with a full path
         match = re.match('^"(.*)"$', value)
         if match != None and match.groups() != None:
            split_val = os.path.split(match.groups()[0])

         # Replace these attributes in the job class ad or the AMI instance
         # will fail.  Need to remove any reference to directories so all
         # files will be put in the temporary execute directory on the
         # machine executing the job
         if attribute.lower() in transfer_attribs and create_sandbox == 'yes':
            # Don't mess with the command if it won't be transfered to
            # the remote system.  This likely means the exe already exists
            # where the job will be executed
            if attribute.lower() == 'cmd' and transfer_exe == 'false':
               new_ad += line + '\n'
               continue
            if split_val[0] == '':
               files.append(iwd + '/' + match.groups()[0].rstrip() + '\n')
            else:
               files.append(match.groups()[0].rstrip() + '\n')
            new_ad += attribute + ' = "' + split_val[1].rstrip() + '"\n'
            continue
         new_ad += line + '\n'
   sqs_data.class_ad = new_ad

   # Add user EC2 specific information to the grid class ad if not set by the
   # route
   if aws_public_key == '':
      if user_aws_public_key != '':
         grid_classad += 'AmazonPublicKey = "%s"\n' % str(user_aws_public_key)
      else:
         syslog.syslog(syslog.LOG_ERR, 'ERROR: No Public Key defined by the job or the route')
         return(FAILURE)
   if aws_private_key == '':
      if user_aws_private_key != '':
         grid_classad += 'AmazonPrivateKey = "%s"\n' % str(user_aws_private_key)
      else:
         syslog.syslog(syslog.LOG_ERR, 'ERROR: No Private Key defined by the job or the route')
         return(FAILURE)
   if aws_key == '':
      if user_aws_key != '':
         grid_classad += 'AmazonAccessKey = "%s"\n' % str(user_aws_key)
         aws_key_file = user_aws_key
      else:
         syslog.syslog(syslog.LOG_ERR, 'ERROR: No Access Key defined by the job or the route')
         return(FAILURE)
   else:
      aws_key_file = aws_key
   if aws_secret == '':
      if user_aws_secret != '':
         grid_classad += 'AmazonSecretKey = "%s"\n' % str(user_aws_secret)
         aws_secret_file = user_aws_secret
      else:
         syslog.syslog(syslog.LOG_ERR, 'ERROR: No Secret Key defined by the job or the route')
         return(FAILURE)
   else:
      aws_secret_file = aws_secret
   if rsa_public_key == '':
      if user_rsa_public_key != '':
         rsa_public_key_file = user_rsa_public_key
      else:
         syslog.syslog(syslog.LOG_ERR, 'ERROR: No Secret Key defined by the job or the route')
         return(FAILURE)
   else:
      rsa_public_key_file = rsa_public_key

   sqs_data.class_ad += 'AmazonAccessKey = "%s"\n' % str(aws_key_file)
   sqs_data.class_ad += 'AmazonSecretKey = "%s"\n' % str(aws_secret_file)

   # Pull the specific keys out of the files
   if os.path.exists(aws_key_file) == False or \
      os.path.exists(aws_secret_file) == False:
      syslog.syslog(syslog.LOG_ERR, 'ERROR: File %s not found' % aws_key_file)
      print 'ERROR: File %s not found' % aws_key_file
      return(FAILURE)
   else:
      key_file = open(aws_key_file, 'r')
      aws_key_val = key_file.readlines()[0].rstrip()
      key_file.close()
      key_file = open(aws_secret_file, 'r')
      aws_secret_val = key_file.readlines()[0].rstrip()
      key_file.close()
   sqs_queue_name = '%s-%s' % (str(aws_key_val), queue_name)

   # Encode the secret key
   val = popen2('openssl rsautl -inkey "%s" -pubin -encrypt' % rsa_public_key_file)
   val[1].write(aws_secret_val)
   val[1].close()
   enc_key = val[0].read().rstrip()
   aws_filename = '/tmp/aws-keys-' + str(os.getpid())
   file = open(aws_filename, 'w')
   file.write(aws_key_val + '\n')
   file.write(base64.encodestring(enc_key).replace('\n','') + '\n')
   file.write(queue_name)
   file.close()
   sqs_data.class_ad += 'AmazonUserDataFile = "%s"\n' % str(aws_filename)
   grid_classad += 'AmazonUserDataFile = "%s"\n' % str(aws_filename)

   # Open the connection to Amazon's S3 and create a key input/output of
   # data
   s3_con = S3Connection(aws_key_val, aws_secret_val)
   s3_bucket_name = '%s-%s' % (str(aws_key_val), bucket_id)
   s3_bucket = s3_con.create_bucket(s3_bucket_name)
   sqs_data.s3_bucket = s3_bucket_name
   grid_classad += 'S3BucketID = "%s"\n' % s3_bucket_name

   # Generate the sandbox if needed and place it into Amazon's S3
   if create_sandbox == 'yes' and transfer_exe == 'true':
      # Tar up the files
      tarfile_name = '/tmp/archive-' + str(os.getpid()) + '.tar.gz'
      data_files = tarfile.open(tarfile_name, 'w:gz')
      for file in files:
         tar_obj = data_files.gettarinfo(file.rstrip())
         file_obj = open(file.rstrip())
         tar_obj.name = os.path.basename(tar_obj.name)
         data_files.addfile(tar_obj, file_obj)
         file_obj.close()
      data_files.close()
      random.seed()
      rand_num = random.randint(1, max_key_id)
      s3_key = Key(s3_bucket)
      if s3_key == None:
         syslog.syslog(syslog.LOG_ERR, 'Error: Unable to access S3 to set job data in S3 bucket %s' % s3_bucket_name)
         print 'Error: Unable to access S3 to set job data in S3 bucket %s' % s3_bucket_name
         os.remove(tarfile_name)
         return(FAILURE)
      else:
         s3_key.key = str(aws_key_val) + '-' + str(rand_num)
         sqs_data.s3_key = s3_key.key
         s3_key.set_contents_from_filename(tarfile_name)
         os.remove(tarfile_name)
         grid_classad += 'S3KeyID = "%s"\n' % s3_key.key

   # Put the original class ad into Amazon's SQS
   message = Message(body=pickle.dumps(sqs_data))
   sqs_con = SQSConnection(aws_key_val, aws_secret_val)
   sqs_queue = sqs_con.create_queue(sqs_queue_name)
   sqs_queue.write(message)
   grid_classad += 'SQSMessageId = "' + str(message.id) + '"\n'

   # Print the Converted Amazon job to stdout
   print grid_classad

   return(SUCCESS)

if __name__ == '__main__':
   sys.exit(main())

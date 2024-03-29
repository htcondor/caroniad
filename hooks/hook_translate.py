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
import re
import pickle
import tarfile
import base64
from popen2 import popen2
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.sqs.connection import SQSConnection
from boto.sqs.message import Message
from boto.exception import BotoServerError
from condorutils import SUCCESS, FAILURE
from condorutils.osutil import grep
from condorutils.readconfig import *
from condorec2e.sqs import *
from condorec2e.region import *

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
                   'qdate', 'remotewallclocktime', 'servertime',
                   'autoclusterid', 'autoclusterattrs', 'currenthosts', 
                   'routedtojobid', 'managed', 'managedmanager', 'periodichold',
                   'periodicremove', 'periodicrelease']
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
   rsa_public_key = ''
   proc_id = ''
   cluster_id = ''
   qdate = ''
   delay = ''
   s3_key = ''
   route_name = ''
   ami = ''
   instance = ''
   resource_url = 'https://ec2.amazonaws.com/'
   region = ''

   # Parse the route information from stdin.
   route = grep('^\[\s*(.*)\s*\]$', sys.stdin.readline())[0]
   for line in route.split(';'):
      match = grep('^([^=]*)\s*=\s*(.*)$', line.strip())
      if match != None and match[0] != None and match[1] != None:
         attribute = match[0].strip().lower()
         val_match = grep('^"(.*)"$', match[1].strip())
         if val_match != None and val_match[0] != None:
            value = val_match[0].strip()
         else:
            value = match[1].strip()
         if attribute == 'name':
            route_name = value
            continue
         if attribute == 'set_amazonpublickey':
            aws_public_key = value
            continue
         if attribute == 'set_amazonprivatekey':
            aws_private_key = value
            continue
         if attribute == 'set_amazonaccesskey':
            aws_key = value
            continue
         if attribute == 'set_amazonsecretkey':
            aws_secret = value
            continue
         if attribute == 'set_amazons3bucketname':
            bucket_id = value
            continue
         if attribute == 'set_rsapublickey':
            rsa_public_key = value
            continue
         if attribute == 'set_amazonamishutdowndelay':
            delay = value
            continue
         if attribute == 'set_amazonamiid':
            ami = value
            continue
         if attribute == 'set_amazoninstancetype':
            instance = value
            continue
         if attribute == 'set_ec2region':
            region = value
            continue

   # Read the original class ad from stdin and store it for submission
   # to SQS.  Additionally, convert it to an EC2 classad for output
   for line in sys.stdin:
      if line.strip() == delim:
         continue
      match = grep('^([^=]*)\s*=\s*(.*)$', line)
      if match != None and match[0] != None and match[1] != None:
         attribute = match[0].strip()
         lower_attr = attribute.lower()
         val_match = grep('^"(.*)"$', match[1].strip())
         if val_match != None and val_match[0] != None:
            value = val_match[0].strip()
         else:
            value = match[1].strip()
         if lower_attr == 'iwd':
            # Remove the IWD from the class ad so the execute directory
            # will be used
            iwd = value
         if lower_attr == 'amazonpublickey':
            if aws_public_key == '':
               user_aws_public_key = value
            continue
         if lower_attr == 'amazonprivatekey':
            if aws_private_key == '':
               user_aws_private_key = value
            continue
         if lower_attr == 'amazonaccesskey':
            if aws_key == '':
               user_aws_key = value
            continue
         if lower_attr == 'amazonsecretkey':
            if aws_secret == '':
               user_aws_secret = value
            continue
         if lower_attr == 'rsapublickey':
            if rsa_public_key == '':
               user_rsa_public_key = value
            continue
         if lower_attr == 'clusterid':
            cluster_id = value
            continue
         if lower_attr == 'procid':
            proc_id = value
            continue
         if lower_attr == 'qdate':
            qdate = value
            continue
         if lower_attr in skip_attribs:
            continue
         sqs_data.class_ad += str(line)

         if lower_attr == 'globaljobid':
            continue
         if lower_attr == 'ec2region':
            if region == '':
               region = value
         if lower_attr == 'jobuniverse':
            grid_classad += 'JobUniverse = 9\n'
            grid_classad += 'Remote_JobUniverse = ' + str(value) + '\n'
            continue
         if lower_attr in int_reset_attribs:
            grid_classad += attribute + ' = 0\n'
            continue
         if lower_attr in float_reset_attribs:
            grid_classad += attribute + ' = 0.0\n'
            continue
         if lower_attr == 'jobstatus':
            grid_classad += attribute + ' = 1\n'
            continue
         if lower_attr == 'exitbysignal':
            grid_classad += attribute + ' = FALSE\n'
            continue
         if lower_attr == 'shouldtransferfiles':
            create_sandbox = value.lower()
            grid_classad += attribute + ' = "NO"\n'
            continue
         if lower_attr == 'transferexecutable':
            transfer_exe = value.lower()
         if lower_attr == 'cmd' or lower_attr == 'command':
            executable = value
            grid_classad += 'Cmd = "EC2: %s: %s"\n' % (route_name, value)
            continue
      grid_classad += str(line)

   job_queue = '%s%s%s' % (cluster_id, proc_id, qdate)
   sqs_data.class_ad += 'AmazonFullSQSQueueName = "%s"\n' % job_queue
   if delay != '':
      sqs_data.class_ad += 'amazonamishutdowndelay = %s\n' % delay
   sqs_data.class_ad += 'WantAWS = False\n'
   grid_classad += 'AmazonFullSQSQueueName = "%s"\n' % job_queue

   # Search through the class ad and make modifications to the files/paths
   # as necessary
   new_ad = ''
   files = []
   for line in sqs_data.class_ad.split('\n'):
      match = grep('^([^=]*)\s*=\s*(.*)$', line)
      if match != None and match[0] != None and match[1] != None:
         attribute = match[0].strip()
         attr_lower = attribute.lower()
         value = match[1].strip()

         # Ignore files in /dev (like /dev/null)
         if grep('^"/dev/.*"', value) != None:
            continue

         # Remove quotes if they exist.  This is a string, so try to split on
         # the '/' character.  If a / exists, it's a file with a full path
         match = grep('^"(.*)"$', value)
         if match != None and match[0] != None:
            split_val = os.path.split(match[0])

         # Replace these attributes in the job class ad or the AMI instance
         # will fail.  Need to remove any reference to directories so all
         # files will be put in the temporary execute directory on the
         # machine executing the job
         if attr_lower in transfer_attribs and create_sandbox == 'yes':
            # Don't mess with the command if it won't be transfered to
            # the remote system.  This likely means the exe already exists
            # where the job will be executed
            if attr_lower == 'cmd' and transfer_exe == 'false':
               new_ad += line + '\n'
               continue
            if split_val[0] == '':
               files.append(iwd + '/' + match[0].strip() + '\n')
            elif os.path.exists(split_val[0]) == False:
               files.append(iwd + '/' + split_val[1] + '\n')
            else:
               files.append(match[0].strip() + '\n')
            new_ad += attribute + ' = "' + split_val[1].strip() + '"\n'
            continue

         # Set stdout/stderr files to be created in the sandox so they will
         # be transfered back if they are actual files.
         if (attr_lower == 'err' or attr_lower == 'out') and \
            value != '/dev/null':
            new_ad += attribute + ' = "' + os.path.basename(split_val[1]) + '"\n'
            continue
            
         new_ad += line + '\n'
   sqs_data.class_ad = new_ad

   # Add user EC2 specific information to the grid class ad if not set by the
   # route
   if aws_public_key == '':
      if user_aws_public_key != '':
         grid_classad += 'AmazonPublicKey = "%s"\n' % str(user_aws_public_key)
      else:
         sys.stderr.write('Error: No Public Key defined by the job or the route')
         return(FAILURE)

   if aws_private_key == '':
      if user_aws_private_key != '':
         grid_classad += 'AmazonPrivateKey = "%s"\n' % str(user_aws_private_key)
      else:
         sys.stderr.write('Error: No Private Key defined by the job or the route')
         return(FAILURE)

   if aws_key == '':
      if user_aws_key != '':
         grid_classad += 'AmazonAccessKey = "%s"\n' % str(user_aws_key)
         aws_key_file = user_aws_key
      else:
         sys.stderr.write('Error: No Access Key defined by the job or the route')
         return(FAILURE)
   else:
      aws_key_file = aws_key

   if aws_secret == '':
      if user_aws_secret != '':
         grid_classad += 'AmazonSecretKey = "%s"\n' % str(user_aws_secret)
         aws_secret_file = user_aws_secret
      else:
         sys.stderr.write('Error: No Secret Key defined by the job or the route')
         return(FAILURE)
   else:
      aws_secret_file = aws_secret

   if rsa_public_key == '':
      if user_rsa_public_key != '':
         rsa_public_key_file = user_rsa_public_key
      else:
         sys.stderr.write('Error: No Secret Key defined by the job or the route')
         return(FAILURE)
   else:
      rsa_public_key_file = rsa_public_key

   sqs_data.class_ad += 'AmazonAccessKey = "%s"\n' % str(aws_key_file)
   sqs_data.class_ad += 'AmazonSecretKey = "%s"\n' % str(aws_secret_file)

   # Pull the specific keys out of the files
   if os.path.exists(rsa_public_key_file) == False:
      sys.stderr.write('Error: Unable to read RSA public key file')
      return(FAILURE)
   elif os.path.exists(aws_key_file) == False or \
      os.path.exists(aws_secret_file) == False:
      sys.stderr.write('Error: Unable to read AWS key files')
      return(FAILURE)
   else:
      try:
        key_file = open(aws_key_file, 'r')
        aws_key_val = key_file.readlines()[0].strip()
        key_file.close()
        key_file = open(aws_secret_file, 'r')
        aws_secret_val = key_file.readlines()[0].strip()
        key_file.close()
        key_file = open(rsa_public_key_file, 'r')
        key_file.close()
      except IOError, e:
        sys.stderr.write("Error:  Unable to open file")
        sys.stderr.write(str(e))
        return(FAILURE)

   sqs_queue_name = '%s-%s' % (str(aws_key_val), job_queue)

   # Encode the secret key
   val = popen2('openssl rsautl -inkey "%s" -pubin -encrypt' % rsa_public_key_file)
   val[1].write(aws_secret_val)
   val[1].close()
   enc_key = val[0].read().strip()
   aws_user_data = '%s|%s|%s|%s' % (aws_key_val, base64.encodestring(enc_key).replace('\n',''), job_queue, region)

   # Determine which grid resource to use.  If the ec2 gahp exists, use that
   # otherwise use the amazon resource
   try:
      gahp = read_condor_config('', ['EC2_GAHP'])['ec2_gahp']
   except:
      gahp = ''

   if gahp != '' and os.path.exists(gahp) == True:
      if region != '':
         resource_url = 'https://ec2.%s.amazonaws.com/' % region

      grid_classad += 'GridResource = "ec2 %s"\n' % resource_url
      grid_classad += 'EC2AccessKeyId = "%s"\n' % aws_key
      grid_classad += 'EC2SecretAccessKey = "%s"\n' % aws_secret
      grid_classad += 'EC2AmiID = "%s"\n' % ami
      grid_classad += 'EC2InstanceType = "%s"\n' % instance
      grid_classad += 'EC2UserData = "%s"\n' % aws_user_data
   else:
      grid_classad += 'GridResource = "amazon %s"\n' % resource_url
      grid_classad += 'AmazonUserData = "%s"\n' % aws_user_data

   # Open the connection to Amazon's S3 and create a key input/output of
   # data
   try:
      s3_con = S3Connection(aws_key_val, aws_secret_val)
   except BotoServerError, error:
      sys.stderr.write('Error: Unable to connect to S3: %s, %s\n' % (error.reason, error.body))
      return(FAILURE)
      
   s3_bucket_name = '%s-%s' % (str(aws_key_val).lower(), bucket_id.lower())
   try:
      s3_bucket = s3_con.create_bucket(s3_bucket_name)
   except BotoServerError, error:
      sys.stderr.write('Error: Unable to create S3 bucket "%s": %s, %s\n' % (s3_bucket_name, error.reason, error.body))
      return(FAILURE)
   sqs_data.s3_bucket = s3_bucket_name
   grid_classad += 'S3BucketID = "%s"\n' % s3_bucket_name

   # Generate the sandbox if needed and place it into Amazon's S3
   if create_sandbox == 'yes' and transfer_exe == 'true':
      # Tar up the files
      tarfile_name = '/tmp/archive-' + str(os.getpid()) + '.tar.gz'
      data_files = tarfile.open(tarfile_name, 'w:gz')
      for file in files:
         if os.path.exists(file.strip()) == True:
            tar_obj = data_files.gettarinfo(file.strip())
            file_obj = open(file.strip())
            tar_obj.name = os.path.basename(tar_obj.name)
            data_files.addfile(tar_obj, file_obj)
            file_obj.close()
         else:
            sys.stderr.write('Error: Unable to find file "%s"\n' % file)
            os.remove(tarfile_name)
            return(FAILURE)
      data_files.close()
      s3_key = Key(s3_bucket)
      if s3_key == None:
         sys.stderr.write('Error: Unable to access S3 to set job data in S3 bucket %s\n' % s3_bucket_name)
         os.remove(tarfile_name)
         return(FAILURE)
      else:
         s3_key.key = '%s-%s' % (str(aws_key_val), job_queue) 
         sqs_data.s3_key = s3_key.key
         try:
            s3_key.set_contents_from_filename(tarfile_name)
         except BotoServerError, error:
            sys.stderr.write('Error: Unable place job data files into S3 bucket %s, key %s: %s, %s\n' % (s3_bucket_name, s3_key.key, error.reason, error.body))
            os.remove(tarfile_name)
            return(FAILURE)
         
         os.remove(tarfile_name)
         grid_classad += 'S3KeyID = "%s"\n' % s3_key.key

   # Put the original class ad into Amazon's SQS
   message = Message(body=pickle.dumps(sqs_data))
   try:
      r_obj = AWSRegion.get_sqs_region(region)
      sqs_con = SQSConnection(aws_key_val, aws_secret_val, region=r_obj)
   except BotoServerError, error:
      sys.stderr.write('Error: Unable to connect to SQS: %s, %s\n' % (error.reason, error.body))
      if s3_key != '':
         try:
            s3_bucket.delete_key(s3_key)
         except BotoServerError, error:
            sys.stderr.write('Error: Unable to remove job data from S3: %s, %s\n')
      return(FAILURE)

   try:
      sqs_queue = sqs_con.create_queue(sqs_queue_name)
      sqs_queue.write(message)
   except BotoServerError, error:
      sys.stderr.write('Error: Unable to write job to SQS queue "%s": %s, %s\n' % (sqs_queue_name, error.reason, error.body))
      if s3_key != '':
         try:
            s3_bucket.delete_key(s3_key)
         except BotoServerError, error:
            sys.stderr.write('Error: Unable to remove job data from S3: %s, %s\n' % (error.reason, error.body))
      return(FAILURE)

   # Print the Converted Amazon job to stdout
   print grid_classad

   return(SUCCESS)

if __name__ == '__main__':
   sys.exit(main())

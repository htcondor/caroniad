#!/usr/bin/python

from boto.sqs.connection import SQSConnection
from boto.sqs.message import Message
from subprocess import *
import time
import pickle

# Get the specified Amazon key information
process = Popen(['cat', '/home/rsquared/.ec2/access_key'], stdout=PIPE)
aws_key_val = process.communicate()[0].rstrip()
process = Popen(['cat', '/home/rsquared/.ec2/secret_access_key'], stdout=PIPE)
aws_secret_val = process.communicate()[0].rstrip()

conn = SQSConnection(aws_key_val, aws_secret_val)
queues = conn.get_all_queues()
for queue in queues:
   m = queue.read(10)
   while m != None:
      print pickle.loads(m.get_body()).class_ad
      queue.delete_message(m)
      m = queue.read(10)
#   conn.delete_queue(queue)

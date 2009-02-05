#!/usr/bin/python

# To use this tool, the environment must have AWS_ACCESS_KEY_ID set to the
# AWS access key and AWS_SECRET_ACCESS_KEY set to the secret access key.

from boto.sqs.connection import SQSConnection
from boto.sqs.message import Message
from subprocess import *
from boto.exception import *
import time
import pickle

conn = SQSConnection()
queues = conn.get_all_queues()
for queue in queues:
   print queue.id
#   print queue.get_attributes()
   m = queue.read(10)
   while m != None:
      try:
         print pickle.loads(m.get_body()).class_ad
      except:
         m = queue.read(10)
         continue
      print
      queue.delete_message(m)
      m = queue.read(10)
   try:
      conn.delete_queue(queue)
   except BotoServerError, error:
      print 'Unable to delete SQS queue %s: %s, %s' % (queue.id, error.reason, error.body)
      pass

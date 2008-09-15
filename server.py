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

import socket
import pickle
import sys
import os
import time
import syslog
import re
import threading
import signal
import zipfile
import getopt
import tarfile
import random
from subprocess import *
from mrg_hooks.functions import *
from aws_common import *
from boto.sqs.connection import SQSConnection
from boto.sqs.message import Message
from boto.s3.connection import S3Connection
from boto.s3.key import Key
from boto.utils import *

class exit_signal(Exception):
   def __init__(self, str):
      self.msg = str

class work_data(object):
   def __init__(self, msg, slot_num):
      self.__SQS_msg__ = msg
      self.__slot__ = slot_num
      self.__access_time__ = time.time()
      self.__access_lock__ = threading.RLock()

   def lock(self, wait=True):
      """Acquires the lock controlling access to the data in the object"""
      if wait == True:
         self.__access_time__ = time.time()
      return(self.__access_lock__.acquire(wait))

   def unlock(self, wait=True):
      """Releases the lock controlling access to the data in the object"""
      if wait == True:
         self.__access_time__ = time.time()
      self.__access_lock__.release()

   def __set_SQS_msg__(self, msg):
      self.__access_time__ = time.time()
      self.__SQS_msg__ = msg

   def __get_SQS_msg__(self):
      self.__access_time__ = time.time()
      return(self.__SQS_msg__)

   SQS_msg = property(__get_SQS_msg__, __set_SQS_msg__)

   def __set_slot__(self, slot_num):
      self.__access_time__ = time.time()
      self.__slot__ = slot_num

   def __get_slot__(self):
      return(self.__slot__)

   slot = property(__get_slot__, __set_slot__)

   def __get_access_time__(self):
      return(self.__access_time__)

   access_time = property(__get_access_time__)

class global_data(object):
   def __init__(self):
      self.__work_list__ = {}
      self.__access_lock__ = threading.RLock()
      self.__total_jobs_running__ = 0

   def lock(self, wait=True):
      """Acquires the lock controlling access to the stored data"""
      return(self.__access_lock__.acquire(wait))

   def unlock(self):
      """Releases the lock controlling access to the stored data"""
      self.__access_lock__.release()

   def add_work(self, key, SQS_msg, slot):
      """Add work information to list of known work items.  Raises a
         general_exception if the key already exists"""
      work = work_data(SQS_msg, slot)
      if self.__find_work__(key) == False:
         self.lock()
         self.__work_list__.update({key:work})
         self.__total_jobs_running__ = self.__total_jobs_running__ + 1
         self.unlock()
      else:
         raise general_exception(syslog.LOG_WARNING, 'Key %s already exists.' % key)

   def remove_work(self, key):
      """Remove work information from the list of known work items and
         returns the work removed.  The work removed will have its lock()
         method called, so the caller of this method must unlock the work
         item when finished.  If the work with the specified key doesn't
         exist, None is returned"""
      if self.__find_work__(key) == True:
         self.lock()
         work = self.__work_list__[key]
         work.lock()
         del self.__work_list__[key]
         self.__total_jobs_running__ = self.__total_jobs_running__ - 1
         self.unlock()
         return(work)
      else:
         return(None)

   def get_work(self, key):
      """Get work information from the list of known work items.  The
         work removed will have its lock() method called, so the caller
         of this method must unlock the work item when finished. If the
         work with the given key doesn't exist, None is returned"""
      if self.__find_work__(key) == True:
         self.lock()
         work = self.__work_list__[key]
         work.lock()
         self.unlock()
         return(work)
      else:
         return(None)

   def slot_in_use(self, slot_num):
      """Returns True if the given slot is currently processing work,
         False otherwise"""
      result = False
      self.lock()
      for work in self.__work_list__.values():
         if work.slot == slot_num:
            result = True
            break
      self.unlock()
      return(result)

   def __find_work__(self, key):
      """Returns True if the desired key exists, False otherwise"""
      self.lock()
      value = self.__work_list__.has_key(key)
      self.unlock()
      return(value)

   def values(self):
      """Returns a list of work_data objects which contains all known
         work information

         Warning: This function will not prevent access to the list of
                  stored data due to its nature of returning a list of
                  all work_data objects currently stored.  To ensure data
                  integrity, the caller must call the lock() and unlock()
                  methods itself """
      return(self.__work_list__.values())

   def get_total_jobs_running(self):
      """Returns the total number of jobs currently running"""
      return(self.__total_jobs_running__)

def time_monitor(msg_list, sock):
   """Monitors how long the system has been running.  If it is idle at
      around 60 minute intervals, it will shut down the system"""
   func_name = "time_monitor"
   first_time = 1
   sleep_time = 3600
   process = Popen(['cat', '/proc/uptime'], stdout=PIPE)
   uptime = int(round(float(process.communicate()[0].rstrip().split()[0])))
   time_from_next_hour = int(round(float((uptime % 3600)/60)))
   print time_from_next_hour
   while True:
      if first_time == 1:
         first_time = 0
         sleep_time = int(3600 - ((time_from_next_hour+1)*60))
      else:
         sleep_time = 3600
      print "sleeping for %d seconds" % sleep_time
      time.sleep(int(sleep_time))
      print msg_list.get_total_jobs_running()
      if msg_list.get_total_jobs_running() < 1:
         # No jobs are being processed, so close the socket and shutdown
         try:
            sock.shutdown(socket.SHUT_RDWR)
         except:
            pass
         sock.close()
         call(['shutdown',  '-h',  '-P',  'now'])

def lease_monitor(msg_list, max_lease_time, interval, log):
   """Monitor all work for lease expiration.  If a lease expired, the work
      is released"""
   func_name = "lease_monitor"
   while True:
      current_time = float(time.time())
      if log == True:
         print '%s: max_lease_time = %s' % (func_name, str(max_lease_time))
         print '%s: Lease check started at %s' % (func_name, str(current_time))
         print '%s: acquiring list lock' % func_name
      msg_list.lock()
      if log == True:
         print '%s: acquired list lock' % func_name
      for item in msg_list.values():
         if log == True:
            print '%s: access time = %s' % (func_name, str(item.access_time))
            print '%s: current time = %s' % (func_name, str(current_time))
         if item.lock(False) == True:
            if (float(item.access_time) + float(max_lease_time)) < current_time:
               # No other thread is accessing this item and the lease has
               # expired, so delete it from the list of known messages and
               # release the lock on the SQS message
               msg_id = item.SQS_msg.id
               if log == True:
                  print '%s: Expiring %s' % (func_name, str(msg_id))
               msg_list.remove_work(msg_id)

               # Release the message so it can be consumed by another process
               item.SQS_msg.change_visibility(1)

               # Need to unlock the item because the remove_work locks it
               item.unlock(False)

            # Need to unlock here even if the message is expired because
            # work_data uses an RLock, which counts the number of times a
            # thread has called the lock mechanism, and at this point lock
            # the lock has been successfully acquired via the lock call above.
            # This lock is irrespective of the lock released if the message
            # has been expired
            item.unlock(False)

      if log == True:
         print '%s: releasing list lock' % func_name
      msg_list.unlock()
      if log == True:
         print '%s: released list lock' % func_name
      time.sleep(int(interval))

def exit_signal_handler(signum, frame):
   raise exit_signal('Exit signal %s received' % signum)

def handle_get_work(req_socket, reply, queue, known_items, log):
   """Retrieve a message from an SQS queue and send it back to the
      requesting client"""
   func_name = "handle_get_work"
   if log == True:
      print '%s called at %s' % (func_name, str(time.localtime()))

   remove_attribs = ['iwd', 'userlog']
   file_attribs = ['err', 'out', 'transferoutput']

   try:
      # Figure out the SlotID that is requesting work, and don't get any
      # more work if it is still processing work from a previous call
      slots = grep('^SlotID\s*=\s*(.+)$', reply.data)
      if slots == None:
         syslog.syslog(syslog.LOG_ERR, 'Unable to determine SlotID for request.')
      else:
         slot = slots[0]

      if log == True:
         print '%s: Checking if slot %s is known' % (func_name, str(slot))
      if known_items.slot_in_use(slot) == True:
         if log == True:
            print '%s: known slot %s' % (func_name, str(slot))
         reply.data = ''
         req_socket.send(pickle.dumps(reply, 2))
         close_socket(req_socket)
         return(SUCCESS)

      # Get the work off the SQS work queue if it exists
      q_msg = queue.read()
      if q_msg != None:
         msg = pickle.loads(q_msg.get_body())
         reply.data = msg.class_ad
         job_run_time = grep('^JobLeaseDuration\s*=\s*(.+)$', reply.data)
#         if job_run_time != None:
#            q_msg.change_visibility(job_run_time[0])
      else:
         reply.data = ''
         req_socket.send(pickle.dumps(reply, 2))
         close_socket(req_socket)
         return(SUCCESS)

      # Remove any attributes we don't want and modify any entries that have
      # file paths that don't exist on the system so that the files will be
      # created in the execute directory
      ad = ''
      for line in reply.data.split('\n'):
         match = grep('^(.*)\s*=\s*(.*)$', line)
         if match != None and match[0] != None:
            if match[0].rstrip().lower() in remove_attribs:
               continue

            # Check the file paths
            if match[1] != None and match[0].rstrip().lower() in file_attribs:
               paths = grep ('^"(.+)"$', match[1])
               if paths != None and paths[0] != None:
                  # We have a quoted string, so split on commas since there
                  # could be multiple files listed
                  add_line = match[0] + ' = "'
                  split = paths[0].split(',')
                  add_comma = 0
                  for file in split:
                     dir = os.path.dirname(file)
                     file_name = os.path.basename(file)
                     if add_comma == 0:
                        add_comma = 1
                     else:
                        add_line += ','

                     if dir == '' or os.path.exists(dir) == False:
                        # This file has no path or the path doesn't exist
                        add_line += file_name
                     else:
                        # File has a full path that exists on the system
                        add_line += file
                  ad += add_line + '"\n'
                  continue
         ad += line + '\n'
      reply.data = ad
         
      # Add attributes to the ClassAd that is sent to the requesting client
      msg_num = str(q_msg.id)
      reply.data += 'SQSMessageId = "' + msg_num + '"\n'
      reply.data += 'WF_REQ_SLOT = "' + slot + '"\n'
      reply.data += 'IsFeatched = TRUE\n'

      # Preserve the work data that was processed so it can be
      # deleted or released as needed
      if log == True:
         print '%s: Adding msg id %s to known items' % (func_name, msg_num)
      known_items.add_work(msg_num, q_msg, slot)
   
      # Send the work to the requesting client
      req_socket.send(pickle.dumps(reply, 2))
      close_socket(req_socket)
      return(SUCCESS)

   except general_exception, error:
      log_messages(error)
      return(FAILURE)

def handle_reply_fetch(msg, queue, known_items, log):
   """Send the data from a reply claim hook to a results SQS queue.  Release
      the lock on the receiving SQS queue in the case of a reject"""
   func_name = "handle_reply_fetch"
   if log == True:
      print '%s called at %s' % (func_name, str(time.localtime()))

   remove_attribs = ['iwd']

   try:
      # Find the SQSMessageId in the message received
      message_ids = grep('^SQSMessageId\s*=\s*"(.+)"$', msg.data)
      if message_ids == None:
         raise general_exception(syslog.LOG_ERR, msg.data, 'Unable to find SQS in exit message')
      else:
         message_id = message_ids[0]

      if msg.type == condor_wf_types.reply_claim_reject:
         saved_work = known_items.remove_work(message_id)
      else:
         saved_work = known_items.get_work(message_id)

      if saved_work == None:
         # Couldn't find the SQS message that corresponds to the SQSMessageId
         # in the exit message.  This is bad and shouldn't happen.
         raise general_exception(syslog.LOG_ERR, 'Unable to find stored SQS message with SQSMessageId %s.' % str(message_id))
      else:
         try:
            # Only want the job ClassAd and not the Slot Class Ad.  Since
            # the job classad is listed first followed by the Slot Class Ad
            # and separated by a series of dashes (-), cycle through the data
            # and look for a number of dashes and then quit.  Also want
            # to remove some attributes that shouldn't have updated data
            # sent to the submitter.
            result_ad = ''
            for line in msg.data.split('\n'):
               match = grep('^(.*)\s*=.*$', line)
               if re.match('---', line) != None:
                  break
               elif match != None and match[0] != None:
                  if match[0].rstrip().lower() in remove_attribs:
                     continue
               result_ad += line + "\n"

            response = pickle.loads(saved_work.SQS_msg.get_body())
            response.class_ad = result_ad

            # Send the results to the appropriate SQS queue
            queue.write(Message(body=pickle.dumps(response)))

            if msg.type == condor_wf_types.reply_claim_reject:
               # Reset the visibility timer so it can be read again quickly.
               saved_work.SQS_msg.change_visibility(1)
         finally:
            if log == True:
               print '%s: Releasing lock on %s' % (func_name, str(message_id))
            saved_work.unlock()

      return(SUCCESS)

   except general_exception, error:
      log_messages(error)
      return(FAILURE)

def handle_prepare_job(req_socket, reply, s3_storage, known_items, log):
   """Prepare the environment for the job.  This includes accessing S3
      for any data specific to the job and providing it to codor's 
      temporary execute directory."""
   func_name = "handle_prepare_job"
   if log == True:
      print '%s called at %s' % (func_name, str(time.localtime()))

   try:
      # Find the SQSMessageId in the message received
      message_ids = grep('^SQSMessageId\s*=\s*"(.+)"$', reply.data)
      if message_ids == None:
         raise general_exception(syslog.LOG_ERR, reply.data, 'Unable to find SQSMessageId in prepare job message')
      else:
         message_id = message_ids[0]

      # Find the Current Working Directory  of the originating process
      # in the message received
      work_cwd = grep('^OriginatingCWD\s*=\s*"(.+)"$', reply.data)[0]

      saved_work = known_items.get_work(message_id)
      if saved_work == None:
         # Couldn't find the SQS message that corresponds to the SQSMessageId
         # in the exit message.  This is bad and shouldn't happen.
         raise general_exception(syslog.LOG_ERR, 'Unable to find stored SQS message with SQSMessageId %s' % str(message_id))
      else:

         try:
            # If the S3 parameters are not None, then there is data to pull
            # from S3 for this job
            msg = pickle.loads(saved_work.SQS_msg.get_body())
            if msg.s3_bucket != None and msg.s3_key != None:
               # Retrive the S3 key from the message
               s3_bucket = s3_storage.get_bucket(msg.s3_bucket)
               s3_key = Key(s3_bucket)
               s3_key.key = msg.s3_key

               # Retrieve the archived file from S3 and put it into the 
               # directory for the job
               input_filename = work_cwd + '/data.tar.gz'
               s3_key.get_contents_to_filename(input_filename)
               reply.data = input_filename
            else:
               reply.data = ''
            
            # Send the information about the archive file to the requester
            req_socket.send(pickle.dumps(reply, 2))
            close_socket(req_socket)
         finally:
            if log == True:
               print '%s: Releasing lock on %s' % (func_name, str(message_id))
            saved_work.unlock()
      return(SUCCESS)

   except general_exception, error:
      log_messages(error)
      return(FAILURE)

def handle_update_job_status(msg, queue, known_items, log):
   """Send the job status update information to a results SQS queue."""
   func_name = "handle_update_job_status"
   if log == True:
      print '%s called at %s' % (func_name, str(time.localtime()))

   remove_attribs = ['iwd']

   try:
      # Find the SQSMessageId in the message received
      message_ids = grep('^SQSMessageId\s*=\s*"(.+)"$', msg.data)
      if message_ids == None:
         raise general_exception(syslog.LOG_ERR, msg.data, 'Unable to find SQSMessageId in exit message')
      else:
         message_id = message_ids[0]

      saved_work = known_items.get_work(message_id)
      if log == True:
         print '%s: Returned from get_work for message %s' % (func_name, str(message_id))
      if saved_work == None:
         # Couldn't find the SQS message that corresponds to the SQSMessageId
         # in the exit message.  This is bad and shouldn't happen.
         raise general_exception(syslog.LOG_ERR, 'Unable to find stored SQS message with SQSMessageId %s' % str(message_id))
      else:

         try:
            # Remove some attributes that shouldn't have updated data
            # sent to the submitter. The Class Ad doesn't reflect the
            # appropriate state, so change it to say the job is running(2).
            result_ad = ''
            for line in msg.data.split('\n'):
               match = grep('^(.*)\s*=.*$', line)
               if match != None and match[0] != None:
                  if match[0].rstrip().lower() in remove_attribs:
                     continue
                  elif match[0].rstrip() == 'JobStatus':
                     result_ad += 'JobStatus = 2\n'
                     continue
               result_ad += line + "\n"

            response = pickle.loads(saved_work.SQS_msg.get_body())
            response.class_ad = result_ad
#            response.class_ad = msg.data

            # Send the results to the appropriate SQS queue
            queue.write(Message(body=pickle.dumps(response)))
         finally:
            if log == True:
               print '%s: Releasing lock on %s' % (func_name, str(message_id))
            saved_work.unlock()
      return(SUCCESS)

   except general_exception, error:
      log_messages(error)
      return(FAILURE)

def handle_exit(req_socket, msg, s3_storage, work_q, results_q, known_items, log):
   """The job exited, so handle the reasoning appropriately.  If the
      job exited normally, then remove the work job from the SQS queue,
      otherwise release the lock on the work.  Always place the results
      on the SQS results queue"""
   func_name = "handle_exit"
   if log == True:
      print '%s called at %s' % (func_name, str(time.localtime()))

   transfer_file_attribs = ['Err', 'Out', 'TransferOutput']
   file_list = []
   remove_attribs = ['iwd']

   try:
      # Determine the slot that is reporting results
      slots = grep ('^WF_REQ_SLOT\s*=\s*"(.+)"$', msg.data)
      if slots == None:
         syslog.syslog(syslog.LOG_WARNING, 'Unable to determine SlotID for results.')
      else:
         # Verify the slot sending results is known to be in use.  If not,
         # somehow results have been send from an unknown slot.
         slot = slots[0]
         if known_items.slot_in_use(slot) == False:
            syslog.syslog(syslog.LOG_WARNING, 'Received exit message from unknown slot %s' % slot)

      # Find the SQSMessageId in the message we received
      message_ids = grep('^SQSMessageId\s*=\s*"(.+)"$', msg.data)
      if message_ids == None:
         raise general_exception(syslog.LOG_ERR, msg.data, 'Unable to find SQSMessageId in exit message')
      else:
         message_id = message_ids[0]

      # Find the Current Working Directory of the originating process
      # in the message received
      work_cwd = grep('^OriginatingCWD\s*=\s*"(.+)"$', msg.data)[0]

      # Retrieve the SQS message from the list of known messages so it
      # can be acknowledged or released
      saved_work = known_items.remove_work(message_id)
      if saved_work == None:
         # Couldn't find the SQS message that corresponds to the SQSMessageId
         # in the exit message.  This is bad and shouldn't happen.
         raise general_exception(syslog.LOG_ERR, 'Unable to find stored SQS message with SQSMessageId %s.  Message cannot be acknowledged nor results sent!' % str(message_id))
      else:

         try:
            # Retrieve the saved classad information for the
            # results message.
            results = pickle.loads(saved_work.SQS_msg.get_body())

            # If the S3 key is None, then there wasn't any input data for this
            # job so we'll need to create a new key to store the data in.
            # Otherwise, reuse the values from the message
            s3_bucket = s3_storage.get_bucket(results.s3_bucket)
            if results.s3_key != None:
               s3_key = s3_bucket.get_key(results.s3_key)
            else:
               random.seed()
               rand_num = random.randint(1, 100000)
               aws_access_key = s3_storage.aws_access_key_id
               s3_key = Key(s3_bucket)
               s3_key.key = str(aws_access_key) + '-' + str(rand_num)
               results.s3_key = s3_key.key

            # Create the list of files to put into the results archive
            orig_cwd = os.getcwd()
            os.chdir(work_cwd)
            file_list += os.listdir(".")
            for attrib in transfer_file_attribs:
               match = grep('^' + attrib + '\s*=\s*"(.+)"$', msg.data)
               if match != None and match[0] != None:
                  for file in match[0].split(','):
                     if file not in file_list:
                        # Only add the file to the list if wasn't there already
                        file_list += file

            # Archive all the important files
            results_filename = work_cwd + '/results.tar.gz'
            results_file = tarfile.open(results_filename, 'w:gz')
            for file in file_list:
               if os.path.exists(file.rstrip()):
                  if os.path.dirname(file.rstrip()) != '':
                     os.chdir(os.path.dirname(file.rstrip()))
                     results_file.add(os.path.basename(file.rstrip()))
                     os.chdir(work_cwd)
                  else:
                     results_file.add(file.rstrip())
            results_file.close()
            os.chdir(orig_cwd)

            if msg.type == condor_wf_types.exit_exit:
               # Job exited normally, so upload the sandbox to S3,
               # and remove the message on the SQS work queue
               if log == True:
                  print '%s: Normal exit' % func_name

               # The Class Ad we have don't reflect the appropriate state, so 
               # change it to say the job is completed(4).  Also remove
               # attributes that shouldn't have updated data sent to the
               # originater.
               result_ad = ''
               start_time = 0
               run_time = 0
               for line in msg.data.split('\n'):
                  match = grep('^(.*)\s*=.*$', line)
                  if re.match('JobStatus', line) != None:
                     result_ad += 'JobStatus = 4\n'
                  else:
                     if match != None and match[0] != None:
                        if match[0].rstrip().lower() in remove_attribs:
                           continue
                     if line != '':
                        result_ad += line + "\n"

                  # Set the job completion time by finding the start time and
                  # job duration from the class ad and add them together.
                  match = re.match('^JobStartDate\s*=\s*(.+)$', line)
                  if match != None and match.groups() != None:
                     start_time = int(match.groups()[0])

                  match = re.match('^JobDuration\s*=\s*(.+)$', line)
                  if match != None and match.groups() != None:
                     run_time = int(round(float(match.groups()[0])))

               result_ad += 'JobFinishedHookDone = ' + str(start_time + run_time) + '\n'
               results.class_ad = result_ad
#               results.class_ad = msg.data

               # Upload the sandbox to S3
               s3_key.set_contents_from_filename(results_filename)

               # Remove the message from the SQS queue
               work_q.delete_message(saved_work.SQS_msg)
            else:
               # Job didn't exit normally
               if log == True:
                  print '%s: Not normal exit: %s' % (func_name, str(msg.type))

               # Reset the visibility timer so it can be read again quickly.
               saved_work.SQS_msg.change_visibility(1)
         finally:
            # Send the results to the appropriate SQS queue
            results_q.write(Message(body=pickle.dumps(results)))
            saved_work.unlock()

      # Send acknowledgement to the originator that exit work is complete
      req_socket.send('Completed')
      close_socket(req_socket)
      return(SUCCESS)

   except general_exception, error:
      log_messages(error)
      return(FAILURE)

def main(argv=None):
   listen_socket = None
   private_key_file = '/root/.ec2/rsa_key'
#   private_key_file = '/home/rsquared/.ec2/private_key'

   if argv is None:
      argv = sys.argv

   try:
      try:
         opts, args = getopt.getopt(argv[1:], 'dh', ['debug', 'help'])
      except getopt.GetoptError, error:
        print str(error)
        return(FAILURE)

      debug_logging = False
      for option, arg in opts:
         if option in ('-d', '--debug'):
            debug_logging = True
         if option in ('-h', '--help'):
            print 'usage: ' + os.path.basename(argv[0]) + ' [-d|--debug] [-h|--help]'
            return(SUCCESS)

      # Open a connection to the system logger
      syslog.openlog(os.path.basename(argv[0]))

      # Set signal handlers
      signal.signal(signal.SIGINT, exit_signal_handler)

      # Read the user data and decrypt to get the access keys
      user_data = get_instance_userdata()
      if user_data == None:
         # TODO: Send message about startup failure
         print "No User Data"
         return(FAILURE)

      file = open('/root/data', 'w')
      file.writelines(user_data)
      file.close()

      process = Popen(['openssl', 'rsautl', '-inkey', private_key_file, '-decrypt', '-in', '/root/data'], stdout=PIPE)
      data = process.communicate()[0].rstrip().split('\n')
      os.remove('/root/data')
      access_key = data[0].rstrip()
      secret_key = data[1].rstrip()
      queue_name = data[2].rstrip()

      try:
         sqs_config = read_config_file('/etc/opt/grid/daemon.conf', 'Daemon')
      except config_err, error:
         raise general_exception(syslog.LOG_ERR, *(error.msg + ('Exiting.','')))

      # Create a container to share data between threads
      share_data = global_data()

      # Open a connection to the AWS SQS service
      sqs_connection = SQSConnection(access_key, secret_key)

      # Create the work queue if it doesn't exist
      work_queue = sqs_connection.create_queue('%s-%s' % (str(access_key), queue_name))

      # Create the status queue if it doesn't exist
      status_queue = sqs_connection.create_queue('%s-%s' % (str(access_key), 'condor_status_queue'))

      # Open a connection to the AWS S3 service
      s3_connection = S3Connection(access_key, secret_key)

      # Create a thread to monitor work expiration times
      monitor_thread = threading.Thread(target=lease_monitor, args=(share_data, sqs_config['lease_time'], sqs_config['lease_check_interval'], debug_logging))
      monitor_thread.setDaemon(True)
      monitor_thread.start()

      # Setup the socket for communication with condor
      listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      try:
         listen_socket.bind((sqs_config['ip'], int(sqs_config['port'])))
         listen_socket.listen(int(sqs_config['queued_connections']))
      except socket.error, error:
         raise general_exception(syslog.LOG_ERR, 'socket error %d: %s' % (error[0], error[1]), 'Failed to listen on %s:%s' % (sqs_config['ip'], sqs_config['port']))

      # Create a thread to shutdown if idle at 60 minute intervals
      timer_thread = threading.Thread(target=time_monitor, args=(share_data, listen_socket))
      timer_thread.setDaemon(True)
      timer_thread.start()

      # Accept all incoming connections and act accordingly
      while True:
       try:
         sock,address = listen_socket.accept()
         recv_data = socket_read_all(sock)
         condor_msg = pickle.loads(recv_data)

         # Set up a child thread to perform the desired action
         if condor_msg.type == condor_wf_types.get_work:
            child = threading.Thread(target=handle_get_work, args=(sock, condor_msg, work_queue, share_data, debug_logging))
         elif condor_msg.type == condor_wf_types.reply_claim_accept or \
              condor_msg.type == condor_wf_types.reply_claim_reject:
            child = threading.Thread(target=handle_reply_fetch, args=(condor_msg, status_queue, share_data, debug_logging))
         elif condor_msg.type == condor_wf_types.prepare_job:
            child = threading.Thread(target=handle_prepare_job, args=(sock, condor_msg, s3_connection, share_data, debug_logging))
         elif condor_msg.type == condor_wf_types.update_job_status:
            child = threading.Thread(target=handle_update_job_status, args=(condor_msg, status_queue, share_data, debug_logging))
         elif condor_msg.type == condor_wf_types.exit_exit or \
              condor_msg.type == condor_wf_types.exit_remove or \
              condor_msg.type == condor_wf_types.exit_hold or \
              condor_msg.type == condor_wf_types.exit_evict:
            child = threading.Thread(target=handle_exit, args=(sock, condor_msg, s3_connection, work_queue, status_queue, share_data, debug_logging))
            # Only handle 1 job
            try:
               listen_socket.shutdown(socket.SHUT_RDWR)
            except:
               pass
            listen_socket.close()
         else:
            syslog.syslog(syslog.LOG_WARNING, 'Received unknown request: %d' % condor_msg.type)
            continue
         child.setDaemon(True)
         child.start()
       except:
         pass

   except exit_signal, exit_data:
      # Close the session before exiting
      if listen_socket != None:
         try:
            listen_socket.shutdown(socket.SHUT_RDWR)
         except:
            pass
         listen_socket.close()
      return(SUCCESS)

   except general_exception, error:
      log_messages(error)
      # Close the session before exiting
      if listen_socket != None:
         try:
            listen_socket.shutdown(socket.SHUT_RDWR)
         except:
            pass
         listen_socket.close()
      return(FAILURE)

if __name__ == '__main__':
    sys.exit(main())

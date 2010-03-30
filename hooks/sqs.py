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

class SQSEntry(object):
   def __init__(self, class_ad='', s3_bucket=None, s3_key=None):
      self.__s3_bucket__ = s3_bucket
      self.__s3_key__ = s3_key 
      self.__class_ad__ = class_ad 
    
   def set_s3_bucket(self, bucket):
      self.__s3_bucket__ = bucket

   def get_s3_bucket(self):
      return self.__s3_bucket__

   s3_bucket = property(get_s3_bucket, set_s3_bucket)

   def set_s3_key(self, bucket):
      self.__s3_key__ = bucket

   def get_s3_key(self):
      return self.__s3_key__

   s3_key = property(get_s3_key, set_s3_key)

   def set_class_ad(self, classad):
      self.__class_ad__ = classad

   def get_class_ad(self):
      return self.__class_ad__

   class_ad = property(get_class_ad, set_class_ad)

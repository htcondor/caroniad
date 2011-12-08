#   Copyright 2011 Red Hat, Inc.
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
import boto.sqs as sqs
from boto.s3.connection import Location

class AWSRegion(object):
   def get_sqs_region(region_name):
      if region_name == '':
         return None

      for obj in sqs.regions():
         if obj.name == region_name:
            region_obj = obj
            break
      return region_obj

   get_sqs_region = staticmethod(get_sqs_region)

   def get_s3_region(region_name):
      region = Location.DEFAULT
      if region_name[0:2].lower() == 'eu':
         region = Location.EU
      else:
         for loc in dir(Location):
           if loc[0:2] == '__':
              continue
           r = getattr(Location, loc)
           if r == region_name:
              region = r
              break
      return region

   get_s3_region = staticmethod(get_s3_region)

   def get_s3_host(region_name):
      host = 's3.amazonaws.com'
      if region_name != '':
         host = 's3-%s.amazonaws.com' % region_name
      return host

   get_s3_host = staticmethod(get_s3_host)

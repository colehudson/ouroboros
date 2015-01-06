from WSUDOR_Manager import *
from localConfig import *

import eulfedora
import json
from json import JSONEncoder
import requests
import bagit
import sys
import os
import glob
import mimetypes
import time


def main(input_dir):

	print "Working on",input_dir	

	filename = input_dir.replace("/","_") + ".errors"	
	filename = filename[1:]

	# get sub-dir bags
	dir_structure = os.walk(input_dir).next()
	root_dir = dir_structure[0]

	# iterate through
	count = 0
	for bag_dir in dir_structure[1]:
		count += 1
		print "Working on",count,"of",len(dir_structure[1])
		try:
			full_bag_path = root_dir+bag_dir
			print "Working on:",full_bag_path

			# open v2 handle
			v2_handle = WSUDOR_ContentTypes.WSUDOR_Object(object_type="bag", payload=full_bag_path)

			# purge v1
			try:
				fedoraHandles.fedora_handle.purge_object(v2_handle.pid)
			except:
				print "v1 Object not found, skipping purge and continuing with v2 ingest."

			# take a breather
			time.sleep(.2)

			# ingest v2
			v2_handle.ingestBag()


		except Exception, e:
			print "An error was had with",full_bag_path
			fhand = open(filename,'a')
			fhand.write("{full_bag_path} - {e}\n".format(full_bag_path=full_bag_path,e=str(e)))
			fhand.close()


# if run as script, go to town
print 'hey there!'
if __name__ == "__main__":
	
	main(sys.argv[1])

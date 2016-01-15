# Python imports
import requests
import ast
import urllib
from paste.util.multidict import MultiDict
import json
import re
import hashlib
import xmltodict
import subprocess
import ldap
import mimetypes
import inspect

# utilities
from utils import *

# config
from localConfig import *

# modules from WSUDOR_Manager
from WSUDOR_Manager.fedoraHandles import fedora_handle
from WSUDOR_Manager.solrHandles import solr_handle
import WSUDOR_ContentTypes

from availableFunctions import *


# class to hold all methods for singleObjectPackage
class SingleObjectMethods(object):	

	def __init__(self, getParams):

		self.getParams = getParams
		self.return_dict = {}

		# get PID
		self.PID = getParams['PID'][0]
		self.PID_suffix = self.PID.split(":")[1]		

		# instantiate WSUDOR object
		self.obj_handle = WSUDOR_ContentTypes.WSUDOR_Object(self.PID)

		# determine if object exists and is active
		if self.obj_handle != False and self.obj_handle.ohandle.exists == True and self.obj_handle.ohandle.state == "A":
			self.active = True
			self.return_dict['isActive'] = {"object_status":"Active"}

			# retrieve Solr doc
			if 'on_demand' in getParams and getParams['on_demand'] == True:
				self.return_dict['objectSolrDoc'] = self.obj_handle.previewSolrDict()
			else:
				self.return_dict['objectSolrDoc'] = self.obj_handle.SolrSearchDoc.asDictionary()

		else:
			self.active = False
			self.return_dict['isActive'] = {"object_status":"Absent"}


	
	# function to return all methods for this package Class
	def runAll(self):		

		for method in inspect.getmembers(self, predicate=inspect.ismethod):		
			if method[0] != "__init__" and method[0] != "runAll":
				print "Running",method[0]
				response_tuple = method[1](self.getParams)
				print response_tuple
				# if not False, add to response
				if response_tuple[1] != False:
					self.return_dict[response_tuple[0]] = response_tuple[1]

		# return return dict
		return self.return_dict



	####################################################################################
	# Components Pieces
	'''
	each sub-component returns a tuple with desired name and results as dictionary,
	via self.runAll() function
	'''	
	####################################################################################


	####################################################################################
	# Generic Components to return
	####################################################################################

	def hasPartOf_comp(self,getParams):
		# runs hasPartOf(), gets components and their representations ()
		# saves to 'hasPartOf'	
		return ("hasPartOf",json.loads(hasPartOf(getParams)))


	def isMemberOfCollection_comp(self,getParams):
		# returns collections the object is a part of
		# saves to 'isMemberOfCollection'
		return ("isMemberOfCollection",json.loads(isMemberOfCollection(getParams)))


	def hasMemberOf_comp(self,getParams):
		print hasMemberOf(getParams)
		# returns collections the object is a part of
		# saves to 'hasMemberOf'
		return ("hasMemberOf",json.loads(hasMemberOf(getParams)))


	def hierarchicalTree_comp(self,getParams):
		print hierarchicalTree(getParams)
		# returns collections the object is a part of
		# saves to 'hasParent'
		return ("hierarchicalTree",json.loads(hierarchicalTree(getParams)))


	####################################################################################
	# WSUDOR_Image ContentType
	####################################################################################

	def main_imageDict_comp(self,getParams):
		# create small dictinoary with image datastreams for main intellectual object
		# saves to 'main_imageDict'
		if self.obj_handle.content_type == "WSUDOR_Image":
			
			# perform query			
			main_imageDict = {
				"thumbnail" : self.return_dict['objectSolrDoc']['rels_isRepresentedBy'][0]+"_THUMBNAIL",
				"preview" : self.return_dict['objectSolrDoc']['rels_isRepresentedBy'][0]+"_PREVIEW",
				"access" : self.return_dict['objectSolrDoc']['rels_isRepresentedBy'][0]+"_ACCESS",				
				"jp2" : self.return_dict['objectSolrDoc']['rels_isRepresentedBy'][0]+"_JP2",
				"original" : self.return_dict['objectSolrDoc']['rels_isRepresentedBy'][0],
			}
			return ("main_imageDict",main_imageDict)

		else:
			return ("main_imageDict", False)


	def parts_imageDict_comp(self,getParams):
		# returns image dictionary for parts, reusing hasPartOf_results
		# saves to 'parts_imageDict'	
		if self.obj_handle.content_type == "WSUDOR_Image":

			# get parts
			handle = json.loads(hasPartOf(getParams))

			parts_imageDict = {}
			parts_imageDict['parts_list'] = []
			for each in handle['results']:			

				parts_imageDict[each['ds_id']] = {
					'ds_id':each['ds_id'],
					'pid':each['pid'],
					'thumbnail' : fedora_handle.risearch.get_subjects("info:fedora/fedora-system:def/relations-internal#isThumbnailOf", "{object}".format(object=each['object'])).next().split("/")[-1],
					'preview' : fedora_handle.risearch.get_subjects("info:fedora/fedora-system:def/relations-internal#isPreviewOf", "{object}".format(object=each['object'])).next().split("/")[-1],
					'jp2' : fedora_handle.risearch.get_subjects("info:fedora/fedora-system:def/relations-internal#isJP2Of", "{object}".format(object=each['object'])).next().split("/")[-1],
					# RIGHT HERE, PUT THE QUERY THAT GRABS THE ORDER THAT WE NOW HAVE AS A RELS-INT #

				}

				# check for order and assign
				try:
					order = int(fedora_handle.risearch.get_objects("{object}".format(object=each['object']), "info:fedora/fedora-system:def/relations-internal#isOrder").next())
				except:
					order = False
				parts_imageDict[each['ds_id']]['order'] = order

				# add to list
				parts_imageDict['parts_list'].append((parts_imageDict[each['ds_id']]['order'],parts_imageDict[each['ds_id']]['ds_id']))
			

			# sort and make iterable list from dictionary
			parts_imageDict['parts_list'].sort(key=lambda tup: tup[0])
			parts_imageList = []
			for each in parts_imageDict['parts_list']:
				parts_imageList.append(parts_imageDict[each[1]])
			
			# reassign		
			del parts_imageDict['parts_list']
			parts_imageDict['sorted'] = parts_imageList


			# debug
			print "DEBUG ------------------->",parts_imageDict
			print "DEBUG ------------------->",parts_imageList

			return ("parts_imageDict",parts_imageDict)

		else:
			return ("parts_imageDict",False)




	####################################################################################
	# WSUDOR_Audio ContentType
	####################################################################################

	def playlist_comprehension(self, getParams):
		# return JSON object of audio objectc PLAYLIST datastream
		
		if self.obj_handle.content_type in ["WSUDOR_Audio"]:
			
			# get JSON from PLAYLIST datastream
			ds_handle = self.obj_handle.ohandle.getDatastreamObject("PLAYLIST")
			playlist_handle = json.loads(ds_handle.content)

			# add symlink URLs
			for each in playlist_handle:

				#MP3 symlink
				mp3_symlink = makeSymLink( self.PID, (each['ds_id']+"_MP3") )
				mp3_symlink_URL = "http://{APP_HOST}/symLinks/".format(APP_HOST=localConfig.APP_HOST)+mp3_symlink['symlink'].split("/")[-1]
				each['streaming_mp3'] = mp3_symlink_URL

				#original DS symlink
				original_symlink = makeSymLink( self.PID, each['ds_id'] )
				original_symlink_URL = "http://{APP_HOST}/symLinks/".format(APP_HOST=localConfig.APP_HOST)+original_symlink['symlink'].split("/")[-1]
				each['streaming_original'] = original_symlink_URL

			return ("playlist",playlist_handle)

		else:
			return ("playlist",False)
	


# function package for singleObject view
# mapping can be found here: https://docs.google.com/spreadsheets/d/1YyOKj1DwmsLDTAU-FsZJUndcPZFGfVn-zdTlyNJrs2Q/edit#gid=0
def singleObjectPackage(getParams):		
	
	# instantiate
	singlePackage = SingleObjectMethods(getParams)

	# object exists, and is active
	if singlePackage.active == True:
		return_dict = singlePackage.runAll()
		return json.dumps(return_dict)

	# fails for whatever reason - does not exist, is not active, etc.
	else:
		return json.dumps(singlePackage.return_dict)



# function package for search view
# mapping can be found here: https://docs.google.com/spreadsheets/d/1DFHm2lfGjrFn5SgmeWeFX6Db3ba1IfX7EvcVbsc_zw0/edit?usp=sharing
def searchPackage(getParams):
	pass







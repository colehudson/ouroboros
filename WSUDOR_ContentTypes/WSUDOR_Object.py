# -*- coding: utf-8 -*-

import os
import mimetypes
import json
import traceback
import sys
from lxml import etree
import tarfile
import uuid
import StringIO
import tarfile
import xmltodict
from lxml import etree
import requests
import time
import ast
import zipfile
import shutil

# library for working with LOC BagIt standard 
import bagit

# celery
from cl.cl import celery

# eulfedora
import eulfedora
from eulfedora import syncutil

# localConfig
import localConfig

# WSUDOR
import WSUDOR_ContentTypes
from WSUDOR_Manager.solrHandles import solr_handle
from WSUDOR_Manager.fedoraHandles import fedora_handle
from WSUDOR_Manager import fedoraHandles
from WSUDOR_Manager import models, helpers, redisHandles, actions, utilities

# derivatives
from inc.derivatives import JP2DerivativeMaker



# class factory, returns WSUDOR_GenObject as extended by specific ContentType
def WSUDOR_Object(payload, orig_payload=False, object_type="WSUDOR"):

	'''	
	Function to determine ContentType, then fire the appropriate subclass to WSUDOR_GenObject
	'''

	try:
		# Future WSUDOR object, BagIt object
		if object_type == "bag":
			
			# prepare new working dir & recall original
			working_dir = "/tmp/Ouroboros/"+str(uuid.uuid4())
			print "object_type is bag, creating working dir at", working_dir
			orig_payload = payload

			'''
			# determine if directory or archive file
			# if dir, copy to, if archive, decompress and copy
			# set 'working_dir' to new location in /tmp/Ouroboros
			'''
			if os.path.isdir(payload):
				print "directory detected, symlinking"				
				# shutil.copytree(payload,working_dir)
				os.symlink(payload, working_dir)

							
			# tar file or gz
			elif payload.endswith(('.tar','.gz')):
				print "tar / gz detected, decompressing"
				tar_handle = tarfile.open(payload,'r')
				tar_handle.extractall(path=working_dir)
				payload = working_dir

			elif payload.endswith('zip'):
				print "zip file detected, unzipping"
				with zipfile.ZipFile(payload, 'r') as z:
					z.extractall(working_dir)

			# if the working dir has a sub-dir, assume that's the object directory proper
			if len(os.listdir(working_dir)) == 1 and os.path.isdir("/".join((working_dir, os.listdir(working_dir)[0]))):
				print "we got a sub-dir"
				payload = "/".join((working_dir,os.listdir(working_dir)[0]))
			else:				
				payload = working_dir
			print "payload is:",payload

			# read objMeta.json
			path = payload + '/data/objMeta.json'
			fhand = open(path,'r')
			objMeta = json.loads(fhand.read())
			# only need content_type
			content_type = objMeta['content_type']

		
		# Active, WSUDOR object
		if object_type == "WSUDOR":

			# check if payload actual eulfedora object or string literal, in latter case, attempt to open eul object
			if type(payload) != eulfedora.models.DigitalObject:
				payload = fedora_handle.get_object(payload)

			if payload.exists == False:
				print "Object does not exist, cannot instantiate as WSUDOR type object."
				return False
			
			# GET WSUDOR_X object content_model
			'''
			This is an important pivot.  We're taking the old ContentModel syntax: "info:fedora/CM:Image", and slicing only the last component off 
			to use, "Image".  Then, we append that to "WSUDOR_" to get ContentTypes such as "WSUDOR_Image", or "WSUDOR_Collection", etc.
			'''
			try:
				content_types = list(payload.risearch.get_objects(payload.uri,'info:fedora/fedora-system:def/relations-external#hasContentModel'))
				if len(content_types) <= 1:
					content_type = content_types[0].split(":")[-1]
				else:
					try:
						# use preferredContentModel relationship to disambiguate
						pref_type = list(payload.risearch.get_objects(payload.uri,'http://digital.library.wayne.edu/fedora/objects/wayne:WSUDOR-Fedora-Relations/datastreams/RELATIONS/content/preferredContentModel'))
						pref_type = pref_type[0].split(":")[-1]
						content_type = pref_type
					except:
						print "More than one hasContentModel found, but no preferredContentModel.  Aborting."
						return False

				content_type = "WSUDOR_"+str(content_type)

			# fallback, grab straight from OBJMETA datastream / only fires for v2 objects
			except:				
				if "OBJMETA" in payload.ds_list:
					print "Race conditions detected, grabbing content_type from objMeta"
					objmeta = json.loads(payload.getDatastreamObject('OBJMETA').content)
					content_type = objmeta['content_type']

		print "Our content type is:",content_type

	except Exception,e:
		print traceback.format_exc()
		print e
		return False
	
	# need check if valid subclass of WSUDOR_GenObject	
	try:
		return getattr(WSUDOR_ContentTypes, str(content_type))(object_type = object_type, content_type = content_type, payload = payload, orig_payload = orig_payload)	
	except:
		print "Could not find appropriate ContentType, returning False."		
		return False



# WSUDOR Generic Object class (designed to be extended by ContentTypes)
class WSUDOR_GenObject(object):

	'''
	This class represents an object already present, or destined, for Ouroboros.  
	"object_type" is required for discerning between the two.

	object_type = 'WSUDOR'
		- object is present in WSUDOR, actions include management and export

	object_type = 'bag'
		- object is present outside of WSUDOR, actions include primarily ingest and validation
	'''	

	# init
	############################################################################################################
	def __init__(self, object_type=False, content_type=False, payload=False, orig_payload=False):

		self.index_on_ingest = True,
		self.struct_requirements = {
			"WSUDOR_GenObject":{
				"datastreams":[
					{
						"id":"THUMBNAIL",
						"purpose":"Thumbnail of image",
						"mimetype":"image/jpeg"
					},								
					{
						"id":"MODS",
						"purpose":"Descriptive MODS",
						"mimetype":"text/xml"
					},
					{
						"id":"RELS-EXT",
						"purpose":"RDF relationships",
						"mimetype":"application/rdf+xml"
					},
					{
						"id":"POLICY",
						"purpose":"XACML Policy",
						"mimetype":"text/xml"
					}
				],
				"external_relationships":[
					"http://digital.library.wayne.edu/fedora/objects/wayne:WSUDOR-Fedora-Relations/datastreams/RELATIONS/content/isDiscoverable",
					"http://digital.library.wayne.edu/fedora/objects/wayne:WSUDOR-Fedora-Relations/datastreams/RELATIONS/content/hasSecurityPolicy"					
				]
			}		
		}
		self.orig_payload = orig_payload
		
		# WSUDOR or BagIt archive for the object returned
		try:			

			# Future WSUDOR object, BagIt object
			if object_type == "bag":
				self.object_type = object_type

				# read objMeta.json
				path = payload + '/data/objMeta.json'
				fhand = open(path,'r')
				self.objMeta = json.loads(fhand.read())
				print "objMeta.json loaded for:",self.objMeta['id'],"/",self.objMeta['label']

				# instantiate bag propoerties
				self.pid = self.objMeta['id']
				self.label = self.objMeta['label']
				self.content_type = content_type # use content_type as derived from WSUDOR_Object factory

				# placeholder for future ohandle
				self.ohandle = None

				# BagIt methods
				self.Bag = bagit.Bag(payload)	
				self.temp_payload = self.Bag.path		
				

			# Active, WSUDOR object
			if object_type == "WSUDOR":

				# check if payload actual eulfedora object or string literal
				if type(payload) != eulfedora.models.DigitalObject:
					payload = fedora_handle.get_object(payload)

				# instantiate WSUDOR propoerties
				self.object_type = object_type
				self.pid = payload.pid
				self.pid_suffix = payload.pid.split(":")[1]
				self.content_type = content_type
				self.ohandle = payload
				# only fires for v2 objects
				if "OBJMETA" in self.ohandle.ds_list:
					self.objMeta = json.loads(self.ohandle.getDatastreamObject('OBJMETA').content)			


		except Exception,e:
			print traceback.format_exc()
			print e



	# Lazy Loaded properties
	############################################################################################################
	'''
	These properties use helpers.LazyProperty decorator, to avoid loading them if not called.
	'''
	
	# MODS metadata
	@helpers.LazyProperty
	def MODS_XML(self):
		return self.ohandle.getDatastreamObject('MODS').content.serialize()

	@helpers.LazyProperty
	def MODS_dict(self):
		return xmltodict.parse(self.MODS_XML)

	@helpers.LazyProperty
	def MODS_Solr_flat(self):
		# flattens MODS with GSearch XSLT and loads as dictionary
		XSLhand = open('inc/xsl/MODS_extract.xsl','r')		
		xslt_tree = etree.parse(XSLhand)
  		transform = etree.XSLT(xslt_tree)
  		XMLroot = etree.fromstring(self.MODS_XML)
		SolrXML = transform(XMLroot)
		return xmltodict.parse(str(SolrXML))
	
	#DC metadata
	@helpers.LazyProperty
	def DC_XML(self):
		return self.ohandle.getDatastreamObject('DC').content.serialize()

	@helpers.LazyProperty
	def DC_dict(self):
		return xmltodict.parse(self.DC_XML)

	@helpers.LazyProperty
	def DC_Solr_flat(self):
		# flattens MODS with GSearch XSLT and loads as dictionary
		XSLhand = open('inc/xsl/DC_extract.xsl','r')		
		xslt_tree = etree.parse(XSLhand)
  		transform = etree.XSLT(xslt_tree)
  		XMLroot = etree.fromstring(self.DC_XML)
		SolrXML = transform(XMLroot)
		return xmltodict.parse(str(SolrXML))

	#RELS-EXT and RELS-INT metadata
	@helpers.LazyProperty
	def RELS_EXT_Solr_flat(self):
		# flattens MODS with GSearch XSLT and loads as dictionary
		XSLhand = open('inc/xsl/RELS-EXT_extract.xsl','r')		
		xslt_tree = etree.parse(XSLhand)
  		transform = etree.XSLT(xslt_tree)
  		# raw, unmodified RDF
  		raw_xml_URL = "http://localhost/fedora/objects/{PID}/datastreams/RELS-EXT/content".format(PID=self.pid)
  		raw_xml = requests.get(raw_xml_URL).text.encode("utf-8")
  		XMLroot = etree.fromstring(raw_xml)
		SolrXML = transform(XMLroot)
		return xmltodict.parse(str(SolrXML))

	@helpers.LazyProperty
	def RELS_INT_Solr_flat(self):
		# flattens MODS with GSearch XSLT and loads as dictionary
		XSLhand = open('inc/xsl/RELS-EXT_extract.xsl','r')		
		xslt_tree = etree.parse(XSLhand)
  		transform = etree.XSLT(xslt_tree)
  		# raw, unmodified RDF
  		raw_xml_URL = "http://localhost/fedora/objects/{PID}/datastreams/RELS-INT/content".format(PID=self.pid)
  		raw_xml = requests.get(raw_xml_URL).text.encode("utf-8")
  		XMLroot = etree.fromstring(raw_xml)
		SolrXML = transform(XMLroot)
		return xmltodict.parse(str(SolrXML))


	# SolrDoc class
	@helpers.LazyProperty
	def SolrDoc(self):
		return models.SolrDoc(self.pid)


	# SolrSearchDoc class
	@helpers.LazyProperty
	def SolrSearchDoc(self):
		return models.SolrSearchDoc(self.pid)


	@helpers.LazyProperty
	def objSizeDict(self):

		'''
		Begin storing in Redis.
		If not stored, generate and store.
		If stored, return.

		Improvement: need to provide method for updating
		'''

		# check Redis for object size dictionary
		r_response = redisHandles.r_catchall.get(self.pid)
		if r_response != None:
			print "object size dictionary located and retrieved from Redis"
			return ast.literal_eval(r_response)

		else:
			print "generating object size dictionary, storing in redis, returning"

			size_dict = {}
			tot_size = 0

			# loop through datastreams, append size to return dictionary
			for ds in self.ohandle.ds_list:
				ds_handle = self.ohandle.getDatastreamObject(ds)
				ds_size = ds_handle.size
				tot_size += ds_size
				size_dict[ds] = ( ds_size, utilities.sizeof_fmt(ds_size) )

			size_dict['total_size'] = (tot_size, utilities.sizeof_fmt(tot_size) )

			# store in Redis
			redisHandles.r_catchall.set(self.pid, size_dict)

			# return 
			return size_dict			
			

	def update_objSizeDict(self):

		# clear from Redis
		print "clearing previous entry in Redis"
		redisHandles.r_catchall.delete(self.pid)

		print "regenerating and returning"
		return self.objSizeDict
		



	# WSUDOR_Object Methods
	############################################################################################################
	# function that runs at end of ContentType ingestBag(), running ingest processes generic to ALL objects
	def finishIngest(self, indexObject=True, gen_manifest=False, contentTypeMethods=[]):

		# as object finishes ingest, it can be granted eulfedora methods, its 'ohandle' attribute
		if self.ohandle != None:
			self.ohandle = fedora_handle.get_object(self.objMeta['id'])

		# pull in BagIt metadata as BAG_META datastream tarball
		temp_filename = "/tmp/Ouroboros/"+str(uuid.uuid4())+".tar"
		tar_handle = tarfile.open(temp_filename,'w')
		for bag_meta_file in ['bag-info.txt','bagit.txt','manifest-md5.txt','tagmanifest-md5.txt']:
			tar_handle.add(self.Bag.path + "/" + bag_meta_file, recursive=False, arcname=bag_meta_file)
		tar_handle.close()
		bag_meta_handle = eulfedora.models.FileDatastreamObject(self.ohandle, "BAGIT_META", "BagIt Metadata Tarball", mimetype="application/x-tar", control_group='M')
		bag_meta_handle.label = "BagIt Metadata Tarball"
		bag_meta_handle.content = open(temp_filename)
		bag_meta_handle.save()
		os.system('rm {temp_filename}'.format(temp_filename=temp_filename))		

		# derive Dublin Core from MODS, update DC datastream
		self.DCfromMODS()

		# Write isWSUDORObject RELS-EXT relationship
		self.ohandle.add_relationship("http://digital.library.wayne.edu/fedora/objects/wayne:WSUDOR-Fedora-Relations/datastreams/RELATIONS/content/isWSUDORObject","True")

		# the following methods are not needed when objects are "passing through"
		if indexObject:
			# generate OAI identifier
			print self.ohandle.add_relationship("http://www.openarchives.org/OAI/2.0/itemID", "oai:digital.library.wayne.edu:{PID}".format(PID=self.pid))

			# affiliate with collection set
			try:
				collections = self.previewSolrDict()['rels_isMemberOfCollection']
				for collection in collections:			
					print self.ohandle.add_relationship("http://digital.library.wayne.edu/fedora/objects/wayne:WSUDOR-Fedora-Relations/datastreams/RELATIONS/content/isMemberOfOAISet", collection)
			except:
				print "could not affiliate with collection"

			# Index in Solr (can override from command by setting self.index_on_ingest to False)
			if self.index_on_ingest != False:
				self.indexToSolr()
			else:
				print "Skipping Solr Index"

			# if gen_manifest set, generate IIIF Manifest
			try:
				if gen_manifest == True:
					self.genIIIFManifest(on_demand=True)
			except:
				print "faild on generating IIIF manifest"

			# index object size
			self.update_objSizeDict()

			# run all ContentType specific methods that were passed here
			print "RUNNING ContentType methods..."
			for func in contentTypeMethods:
				func()

		# CLEANUP
		# delete temp_payload, might be dir or symlink
		try:
			print "removing temp_payload directory"
			shutil.rmtree(self.temp_payload)
		except OSError, e:
			# might be symlink
			print "removing temp_payload symlink"
			os.unlink(self.temp_payload)

		# finally, return
		return True


	def exportBag(self, job_package=False, returnTargetDir=False, includeRELS=False):

		'''
		Target Example:
		.
		├── bag-info.txt
		├── bagit.txt
		├── data
		│   ├── datastreams
		│   │   ├── roots.jpg
		│   │   └── trunk.jpg
		│   ├── MODS.xml
		│   └── objMeta.json
		├── manifest-md5.txt
		└── tagmanifest-md5.txt		
		'''
		
		# get PID
		PID = self.pid

		# create temp dir structure
		working_dir = "/tmp/Ouroboros/export_bags"
		# create if doesn't exist
		if not os.path.exists("/tmp/Ouroboros/export_bags"):
			os.mkdir("/tmp/Ouroboros/export_bags")

		temp_dir = working_dir + "/" + str(uuid.uuid4())
		time.sleep(.25)
		os.system("mkdir {temp_dir}".format(temp_dir=temp_dir))
		time.sleep(.25)
		os.system("mkdir {temp_dir}/data".format(temp_dir=temp_dir))
		time.sleep(.25)
		os.system("mkdir {temp_dir}/data/datastreams".format(temp_dir=temp_dir))

		# move bagit files to temp dir, and unpack
		bagit_files = self.ohandle.getDatastreamObject("BAGIT_META").content
		bagitIO = StringIO.StringIO(bagit_files)
		tar_handle = tarfile.open(fileobj=bagitIO)
		tar_handle.extractall(path=temp_dir)		

		# export datastreams based on DS ids and objMeta / requires (ds_id,full path filename) tuples to write them
		def writeDS(write_tuple):
			ds_id=write_tuple[0]
			print "WORKING ON",ds_id

			ds_handle = self.ohandle.getDatastreamObject(write_tuple[0])

			# skip if empty (might have been removed / condensed, as case with PDFs)
			if ds_handle.content != None:

				# XML ds model
				if isinstance(ds_handle,eulfedora.models.XmlDatastreamObject):
					print "FIRING XML WRITER"
					with open(write_tuple[1],'w') as fhand:
						fhand.write(ds_handle.content.serialize())

				# generic ds model (isinstance(ds_handle,eulfedora.models.DatastreamObject))
				else:
					print "FIRING GENERIC WRITER"
					with open(write_tuple[1],'wb') as fhand:
						fhand.write(ds_handle.content)

			else:
				print "Content was NONE for",ds_id,"- skipping..."


		# write original datastreams
		for ds in self.objMeta['datastreams']:
			writeDS((ds['ds_id'],"{temp_dir}/data/datastreams/{filename}".format(temp_dir=temp_dir, filename=ds['filename'])))


		# include RELS
		if includeRELS == True:
			for ds in ['RELS-EXT','RELS-INT']:
				writeDS((ds['ds_id'],"{temp_dir}/data/datastreams/{filename}".format(temp_dir=temp_dir, filename=ds['filename'])))


		# write MODS and objMeta files
		simple = [
			("MODS","{temp_dir}/data/MODS.xml".format(temp_dir=temp_dir)),
			("OBJMETA","{temp_dir}/data/objMeta.json".format(temp_dir=temp_dir))
		]
		for ds in simple:
			writeDS(ds)

		# tarball it up
		named_dir = self.pid.replace(":","-")
		os.system("mv {temp_dir} {working_dir}/{named_dir}".format(temp_dir=temp_dir, working_dir=working_dir, named_dir=named_dir))
		orig_dir = os.getcwd()
		os.chdir(working_dir)
		os.system("tar -cvf {named_dir}.tar {named_dir}".format(working_dir=working_dir, named_dir=named_dir))
		os.system("rm -r {working_dir}/{named_dir}".format(working_dir=working_dir, named_dir=named_dir))

		# move to web accessible location, with username as folder
		if job_package != False:
			username = job_package['username']
		else:
			username = "consoleUser"
		target_dir = "/var/www/wsuls/Ouroboros/export/{username}".format(username=username)
		if os.path.exists(target_dir) == False:
			os.system("mkdir {target_dir}".format(target_dir=target_dir))
		os.system("mv {named_dir}.tar {target_dir}".format(named_dir=named_dir,target_dir=target_dir))

		# jump back to origina working dir
		os.chdir(orig_dir)

		if returnTargetDir == True:
			return "{target_dir}/{named_dir}.tar".format(target_dir=target_dir,named_dir=named_dir)
		else:
			return "http://{APP_HOST}/Ouroboros/export/{username}/{named_dir}.tar".format(named_dir=named_dir,username=username,APP_HOST=localConfig.APP_HOST)


	# reingest bag
	def reingestBag(self, removeExportTar = False):
		
		# get PID
		PID = self.pid

		print "Roundrip Ingesting:",PID

		# export bag, returning the file structure location of tar file
		export_tar = self.exportBag(returnTargetDir=True)
		print "Location of export tar file:",export_tar

		# purge self
		fedora_handle.purge_object(PID)

		# reingest exported tar file
		actions.bagIngest.ingestBag(actions.bagIngest.payloadExtractor(export_tar,'single'))

		# delete exported tar
		if removeExportTar == True:
			print "Removing export tar..."
			os.remove(export_tar)

		# return 
		return PID,"Reingested."



	# Solr Indexing
	def indexToSolr(self, printOnly=False):
		return actions.solrIndexer.solrIndexer('modifyObject', self.pid, printOnly)


	def previewSolrDict(self):
		'''
		Function to run current WSUDOR object through indexSolr() transforms
		'''
		try:
			return actions.solrIndexer.solrIndexer('modifyObject', self.pid, printOnly=True)
		except:
			print "Could not run indexSolr() transform."
			return False



	# regnerate derivative JP2s 
	def regenJP2(self):
		'''
		Function to recreate derivative JP2s based on JP2DerivativeMaker class in inc/derivatives
		Operates with assumption that datastream ID "FOO_JP2" is derivative as datastream ID "FOO"
		
		A lot are failing because the TIFFS are compressed, are PNG files.  We need a secondary attempt
		that converts to uncompressed TIFF first.

		'''

		# iterate through datastreams and look for JP2s	
		jp2_ds_list = [ ds for ds in self.ohandle.ds_list if self.ohandle.ds_list[ds].mimeType == "image/jp2" ]	

		count = 0
		for ds in jp2_ds_list:
			
			print "converting %s, %s / %s" % (ds,str(count),str(len(jp2_ds_list)))
			count += 1

			# init JP2DerivativeMaker
			j = JP2DerivativeMaker(inObj=self)

			# jp2 handle
			jp2_ds_handle = self.ohandle.getDatastreamObject(ds)

			# get original ds_handle 
			orig = ds.split("_JP2")[0]
			try:
				orig_ds_handle = self.ohandle.getDatastreamObject(orig)
			except:
				print "could not find original for",orig					

			# write temp original and set as inPath
			j.inPath = j.writeTempOrig(orig_ds_handle)

			# gen temp new jp2
			print "making JP2 with",j.inPath,"to",j.outPath
			makeJP2result = j.makeJP2()

			# if fail, try again by uncompressing original temp file
			if makeJP2result == False:
				print "trying again with uncompressed original"
				j.uncompressOriginal()
				makeJP2result = j.makeJP2()

			# last resort, pause, try again
			if makeJP2result == False:
				time.sleep(3)
				makeJP2result = j.makeJP2()

			# write new JP2 datastream
			if makeJP2result:
				with open(j.outPath) as fhand:
					jp2_ds_handle.content = fhand.read()
				print "Result for",ds,jp2_ds_handle.save()
				# cleanup
				j.cleanupTempFiles()					

			else:
				# cleanup
				# j.cleanupTempFiles()
				raise Exception("Could not regen JP2")	



	# regnerate derivative JP2s 
	def regen_objMeta(self):
		'''
		Function to regen objMeta.  When we decided to let the bag info stored in Fedora not validate,
		opened up the door for editing the objMeta file if things change.

		Add non-derivative datastreams to objMeta, remove objMeta datastreams that no longer exist		
		'''

		# get list of current datastreams, sans known derivatives
		new_datastreams = []
		prunable_datastreams = []
		original_datastreams = [ ds['ds_id'] for ds in self.objMeta['datastreams'] ]
		known_derivs = [
			'BAGIT_META',
			'DC',
			'MODS',
			'OBJMETA',
			'POLICY',
			'PREVIEW',
			'RELS-EXT',
			'RELS-INT',
			'THUMBNAIL',
			'HTML_FULL'
		]
		known_suffixes = [
			'_JP2',
			'_PREVIEW',
			'_THUMBNAIL',
			'_ACCESS'
		]

		# look for new datastreams not present in objMeta
		for ds in self.ohandle.ds_list:
			if ds not in known_derivs and len([suffix for suffix in known_suffixes if ds.endswith(suffix)]) == 0 and ds not in original_datastreams:
				new_datastreams.append(ds)
		print "new datastreams:",new_datastreams

		# add new datastream to objMeta
		for ds in new_datastreams:
			ds_handle = self.ohandle.ds_list[ds]
			new_ds = {
				'ds_id':ds,
				'filename':ds,
				'internal_relationships':{},
				'label':ds_handle.label,
				'mimetype':ds_handle.mimeType
			}
			self.objMeta['datastreams'].append(new_ds)

		# look for datastreams in objMeta that should be removed
		for ds in self.objMeta['datastreams']:
			if ds['ds_id'] not in self.ohandle.ds_list:
				prunable_datastreams.append(ds['ds_id'])
		print "prunable datastreams",prunable_datastreams

		# prune datastream from objMeta
		self.objMeta['datastreams'] = [ ds for ds in self.objMeta['datastreams'] if ds['ds_id'] not in prunable_datastreams ]

		# resulting objMeta datastreams
		print "Resulting objMeta datastreams",self.objMeta['datastreams']	

		# write current objMeta to fedora datastream
		objMeta_handle = self.ohandle.getDatastreamObject('OBJMETA')
		objMeta_handle.content = json.dumps(self.objMeta)		
		objMeta_handle.save()


	# refresh object
	def objectRefresh(self):

		'''
		Function to update / refresh object properties requisite for front-end.
		Runs multiple object methods under one banner.

		Includes following methods:
		- generate IIIF manifest --> self.genIIIFManifest()
		- update object size in Solr --> self.update_objSizeDict()
		- index in Solr --> self.indexToSolr()
		'''

		try:
			# index in Solr
			self.indexToSolr()

			# generate IIIF manifest
			self.genIIIFManifest()

			# update object size in Solr
			self.update_objSizeDict()

			return True
			
		except:
			return False


	# method to send object to remote repository
	def sendObject(self, dest_repo, export_context='migrate', overwrite=False, show_progress=True, refresh_remote=True):		

		# use syncutil
		print "sending object..."
		result = syncutil.sync_object(
			self.ohandle,
			fedoraHandles.remoteRepo(dest_repo),
			export_context=export_context,
			overwrite=overwrite,
			show_progress=show_progress)

		# refresh object in remote repo (requires refreshObject() method in remote Ouroboros)
		if refresh_remote:
			print "refreshing remote object in remote repository"
			refresh_remote_url = '%s/tasks/objectRefresh/%s' % (localConfig.REMOTE_REPOSITORIES[dest_repo]['OUROBOROS_BASE_URL'], self.pid)
			print refresh_remote_url
			r = requests.get( refresh_remote_url )
			print r.content
		else:
			print "skipping remote refresh"



	################################################################
	# Consider moving
	################################################################
	# derive DC from MODS
	def DCfromMODS(self):
		
		# 1) retrieve MODS		
		MODS_handle = self.ohandle.getDatastreamObject('MODS')		
		XMLroot = etree.fromstring(MODS_handle.content.serialize())

		# 2) transform downloaded MODS to DC with LOC stylesheet
		print "XSLT Transforming: {PID}".format(PID=self.pid)
		# Saxon transformation
		XSLhand = open('inc/xsl/MODS_to_DC.xsl','r')		
		xslt_tree = etree.parse(XSLhand)
		transform = etree.XSLT(xslt_tree)
		DC = transform(XMLroot)		

		# 3) save to DC datastream
		DS_handle = self.ohandle.getDatastreamObject("DC")
		DS_handle.content = str(DC)
		derive_results = DS_handle.save()
		print "DCfromMODS result:",derive_results
		return derive_results



	



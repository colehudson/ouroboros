#!/usr/bin/env python
import requests
import json
import sys
import ast
import os
import xml.etree.ElementTree as ET
import urllib, urllib2
import datetime
from lxml import etree
from flask import Blueprint, render_template, redirect, abort, request, session

from fedoraManager2.fedoraHandles import fedora_handle
from fedoraManager2.jobs import getSelPIDs
from fedoraManager2 import utilities
from fedoraManager2.WSUDORbag import WSUDORbag


exportObject = Blueprint('exportObject', __name__, template_folder='templates', static_folder="static")

'''
This action is designed to export a given object as a WSUDOR objectBag, an instance of LOC's BagIt standard.
'''

@exportObject.route('/exportObject')
@utilities.objects_needed
def index():
	
	'''
	temporarily pushing to /var/www/wsuls/dev/graham/dropbox
	'''

	# get PIDs	
	PIDs = getSelPIDs()

	return render_template("exportObject.html")



def exportObject_worker(job_package):	

	print "Here we go!"
	
	# get PID
	PID = job_package['PID']
	ohandle = fedora_handle.get_object(PID)

	# get WSUDORbag handle
	WSUDORbag_handle = WSUDORbag(ohandle)
	export_result = WSUDORbag_handle.exportObjectBag()

	return export_result

	



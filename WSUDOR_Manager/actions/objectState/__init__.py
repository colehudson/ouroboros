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
from flask import Blueprint, render_template, redirect, abort

from WSUDOR_Manager.fedoraHandles import fedora_handle
from WSUDOR_Manager import utilities


objectState = Blueprint('objectState', __name__, template_folder='templates', static_folder="static")


@objectState.route('/objectState')
@utilities.objects_needed
def index():	
	return render_template("objectState.html")



def objectState_worker(job_package):
	form_data = job_package['form_data']
	print form_data

	# in confirmation present, change state
	if form_data['confirm_string'] == "CONFIRM":

		# grab target state
		target_state = form_data['target_state']

		# set state	
		print "Setting state to: {target_state}".format(target_state=target_state)
		
		# get PID handle, set state, save()
		PID = job_package['PID']		
		obj_ohandle = fedora_handle.get_object(PID)		
		obj_ohandle.state = target_state
		return obj_ohandle.save()

	else:
		return "Confirmation not entered correctly, skipping."



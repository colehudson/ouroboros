# TASK: CreateManifest - Create Manifest

# handles
from WSUDOR_Manager.forms import createManifestForm
from WSUDOR_Manager import utilities
from flask import Blueprint, render_template, request, jsonify, redirect, session, Response, json
import re
import requests
import collections
from WSUDOR_Manager.models import ObjMeta

createManifest = Blueprint('createManifest', __name__, template_folder='templates', static_folder="static")


@createManifest.route('/createManifest')
@utilities.objects_needed
def index():

	form = createManifestForm()
	return render_template("createManifest.html",form=form)

@createManifest.route('/stagingManifest', methods=['GET', 'POST'])
def stagingManifest():
	if request.method == 'GET':
		return redirect("/tasks/createManifest", code=302)

	if request.method == 'POST':
		# Create initial ObjMeta model
		form_data = {
		'id' : request.form['objID'],
		'label' : request.form['objLabel'],
		'policy' : str(json.loads(request.form['lockDown'])['object']),
		'content_type' : "WSUDOR_"+str(json.loads(request.form['contentModel'])['object']).replace('info:fedora/CM:',''),
		'object_relationships' : [
			json.loads(request.form['isDiscoverable']),
			json.loads(request.form['lockDown']),
			json.loads(request.form['contentModel'])
		],
		'datastreams' : []
		}


		# Extract datastreams and place into ObjMeta model/form_data dictionary
		f = request.form
		temp_dictionary = {}
		# grab all things that have integers
		for key, value in f.iteritems():
			integer = re.search(r'\d+$', key)
			if integer is not None:
				integer = integer.group()
				if integer in temp_dictionary.keys():
					pass
				else:
					temp_dictionary[integer] = {}

				key = re.sub('\_'+str(integer)+'$', '', key)
				temp_dictionary[integer][key] = value

				if key.startswith('isRepresentedBy'):
					# make sure it doesn't exist in already
					if 'isRepresentedBy' in form_data:
						pass
					else:
						form_data['isRepresentedBy'] = temp_dictionary[integer]['dsID']
					# now, delete it out of the temp_dictionary
					temp_dictionary[integer].pop(key, None)
		for key, value in temp_dictionary.iteritems():
			form_data['datastreams'].append(value)


		# adds a blank 'isRepresentedBy' in ObjMeta if no datastream has been selected for this
		if 'isRepresentedBy' in form_data:
			pass
		else:
			form_data['isRepresentedBy'] = ''

		# Instantiate the ObjMeta class; form_data will become individual attributes of the object
		objMeta = ObjMeta(**form_data)

		# Push form_data into a session cookie
		session['objMetaManifestData'] = form_data
		objMeta.downloadFile(form_data)

		return render_template("stagingManifest.html", form_data=form_data)

@createManifest.route('/previewManifest', methods=['GET', 'POST'])
def previewManifest():
	if request.method == 'POST':
		form_data = session['objMetaManifestData']
		objMeta = ObjMeta(**form_data)
		return objMeta.displayJSONWeb(form_data)

@createManifest.route('/downloadManifest', methods=['GET', 'POST'])
def downloadManifest():
	if request.method == 'POST':
		form_data = session['objMetaManifestData']
		objMeta = ObjMeta(**form_data)
		return objMeta.downloadFile(form_data)

@createManifest.route('/mimeTypeSearch', methods=['GET', 'POST'])
def mimeTypeSearch():
	if request.method == 'GET':
		return render_template("mimeTypeSearch.html")
	if request.method == 'POST':
		type = request.form['type']
		response = requests.get("http://digital.library.wayne.edu/WSUAPI?functions%5B%5D=mimetypeDictionary&direction=extension2mime&inputFilter="+type)
		return jsonify(**response.json())
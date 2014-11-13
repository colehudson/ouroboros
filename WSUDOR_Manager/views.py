# fm2
from WSUDOR_Manager import app
from WSUDOR_Manager import models
from WSUDOR_Manager import db
from WSUDOR_Manager.actions import actions
from WSUDOR_Manager import redisHandles
from WSUDOR_Manager import login_manager

# python modules
import time
import json
import pickle
import sys
from uuid import uuid4
import json
import unicodedata
import shlex, subprocess
import socket
import hashlib
import os

# flask proper
from flask import render_template, request, session, redirect, make_response, Response, Blueprint
from flask.ext.sqlalchemy import SQLAlchemy
from datetime import datetime

# fm2
from WSUDOR_Manager import app
from WSUDOR_Manager import models
from WSUDOR_Manager import db
from WSUDOR_Manager.actions import actions
from WSUDOR_Manager import redisHandles
import utilities

# login
from flask import flash, url_for, abort, g
from flask.ext.login import login_user, logout_user, current_user, login_required

# models
from models import User, ROLE_USER, ROLE_ADMIN

# forms
from flask_wtf import Form
from wtforms import TextField

# get celery instance / handle
from cl.cl import celery
import jobs
import forms
from redisHandles import *

# localConfig
import localConfig

# Solr
from solrHandles import solr_handle

# Fedora
from fedoraHandles import fedora_handle

# session data secret key
####################################
app.secret_key = 'WSUDOR'
####################################




# META
#########################################################################################################




# GENERAL
#########################################################################################################

@app.route("/")
def index():
	if "username" in session:
		username = session['username']		
		return redirect("userPage")
	else:
		username = "User not set."
		return render_template("index.html",username=username)


@app.route("/about")
def about():

	return render_template("about.html")


@app.route('/userPage')
@login_required
def userPage():
	# set username in session
	username = session['username']

	# info to render page
	userData = {}
	userData['username'] = username
	return render_template("userPage.html",userData=userData)	


@app.route('/systemStatus')
@login_required
def systemStatus():

	#check important ports
	imp_ports = [(61616,"Fedora JMS"),(61617,"WSUAPI - prod"),(61618,"imageServer - prod"),(61619,"WSUAPI - dev"),(61620,"imageServer - dev"),(8080,"Tomcat"),(5001,"Ouroboros dev @:5001"),(5002,"Ouroboros dev @:5002"),(5004,"Ouroboros prod @:5004"),(6379,"Redis"),(3306,"MySQL")]
	
	imp_ports_results = []
	for port,desc in imp_ports:
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		check = result = s.connect_ex(("localhost",port))
		if check == 0:
			msg = "active"
		else:
			msg = "inactive"

		imp_ports_results.append((str(port),desc,msg))	

	return render_template("systemStatus.html",imp_ports_results=imp_ports_results)


# MAJOR SUB-SECTIONS	
#########################################################################################################
@app.route('/contentModels', methods=['GET', 'POST'])
def contentModels():
	
	# get all registered Content Models
	CM_list = fedora_handle.risearch.sparql_query("select $label $CM from <#ri> where { \
		$CM <fedora-rels-ext:isMemberOfCollection> <info:fedora/CM:ModelsCollection> . \
		$CM <info:fedora/fedora-system:def/model#label> $label . \
		}")

	return render_template("contentModels.html",CM_list=CM_list)

@app.route('/MODSedit', methods=['GET', 'POST'])
def MODSedit():
	return render_template("MODSedit.html")

@app.route('/datastreamManagement', methods=['GET', 'POST'])
def datastreamManagement():
	return render_template("datastreamManagement.html")

@app.route('/objectManagement', methods=['GET', 'POST'])
def objectManagement():
	return render_template("objectManagement.html")

@app.route('/serverManagement', methods=['GET', 'POST'])
def serverManagement():
	return render_template("serverManagement.html")

# LOGIN
#########################################################################################################
# Use @login_required when you want to lock down a page

@login_manager.user_loader
def user_loader(userid):
	'''Flask-Login user_loader callback.
	The user_loader function asks this function to get a User Object or return 
	None based on the userid.
	The userid was stored in the session environment by Flask-Login.  
	user_loader stores the returned User object in current_user during every 
	flask request. 
	'''
	return User.query.get(int(userid))


@app.before_request
def before_request():	
	# This is executed before every request
	g.user = current_user



@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
	if request.method == 'POST':
		user = User(request.form['username'] , request.form['password'], request.form['email'])
		db.session.add(user)
		db.session.commit()
		flash('User successfully registered')
		return redirect(url_for('login'))

	elif request.method == 'GET': 
		return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'GET':
		return render_template('login.html')
	username = request.form['username']
	password = request.form['password']
	registered_user = User.query.filter_by(username=username,password=password).first()
	if registered_user is None:
		flash('Username or Password is invalid' , 'error')
		return redirect(url_for('login'))
	login_user(registered_user)
	flash('Logged in successfully')
	session["username"] = username
	return redirect(request.args.get('next') or url_for('index'))


@app.route('/logout')
def logout():
	session["username"] = ""
	logout_user()
	return redirect(url_for('index'))



# JOB MANAGEMENT
#########################################################################################################

# confirmation page for objects, serializes relevant request objects as "job_package"
@app.route("/fireTask/<task_name>", methods=['POST', 'GET'])
@utilities.objects_needed
def fireTask(task_name):

	username = session['username']

	# create job_package	
	job_package = {		
		"username":username,
		"form_data":request.values			
	}

	# pass along binary uploaded data if included in job task
	if 'upload' in request.files and request.files['upload'].filename != '':
		job_package['upload_data'] = request.files['upload'].read()

	task_inputs_key = username+"_"+task_name+"_"+str(int(time.time()))
	print "Assigning to Redis-Cached key:",task_inputs_key
	redisHandles.r_job_handle.set(task_inputs_key,pickle.dumps(job_package))

	# get PIDs to confirm
	PIDs = jobs.getSelPIDs()		

	return render_template("objConfirm.html",task_name=task_name,task_inputs_key=task_inputs_key,PIDs=PIDs,username=username,localConfig=localConfig)


# confirmation page for objects, serializes relevant request objects as "job_package"
@app.route("/cancelTask/<task_inputs_key>", methods=['POST', 'GET'])
def cancelTask(task_inputs_key):

	print redisHandles.r_job_handle.delete(task_inputs_key)
	return redirect("/userPage")


# fireTaskWorker is the factory that begins tasks from WSUDOR_Manager.actions
@app.route("/fireTaskWorker/<task_name>/<task_inputs_key>", methods=['POST', 'GET'])
@utilities.objects_needed
def fireTaskWorker(task_name,task_inputs_key):

	print "Starting task request..."

	# get job_package and burn it
	job_package = pickle.loads(redisHandles.r_job_handle.get(task_inputs_key))
	redisHandles.r_job_handle.delete(task_inputs_key)

	# check if task in available tasks, else abort
	try:
		task_handle = getattr(actions, task_name)
	except:		 
		return utilities.applicationError("Task not found, or user not authorized to perform.  Return to <a href='/userPage'>user page</a>.")		
	
	# get username from session (will pull from user auth session later)
	username = session['username']	

	# get user-selectedd objects	
	stime = time.time()
	userSelectedPIDs = models.user_pids.query.filter_by(username=username,status=True)	
	PIDlist = [PID.PID for PID in userSelectedPIDs]	
	etime = time.time()
	ttime = (etime - stime) * 1000
	print "Took this long to create list from SQL query",ttime,"ms"	

	# instantiate job number
	''' pulling from incrementing redis counter, considering MySQL '''
	job_num = jobs.jobStart()		
	
	# begin job and set estimated tasks
	print "Antipcating",userSelectedPIDs.count(),"tasks...."	
	redisHandles.r_job_handle.set("job_{job_num}_est_count".format(job_num=job_num),userSelectedPIDs.count())	

	# augment job_package
	job_package['job_num'] = job_num

	# send to celeryTaskFactory in actions.py
	'''
	iterates through PIDs and creates secondary async tasks for each
	passing username, task_name, and job_package containing all the update handles	
	'celery_task_id' below contains celery task key, that contains all eventual children objects
	'''
	celery_task_id = actions.celeryTaskFactory.delay(job_num=job_num,task_name=task_name,job_package=job_package,PIDlist=PIDlist)	

	# send job to user_jobs SQL table
	db.session.add(models.user_jobs(job_num, username, celery_task_id, "init"))	
	db.session.commit() 

	print "Started job #",job_num,"Celery task #",celery_task_id	
	return redirect("/userJobs")


#status of currently running, spooling, or pending jobs for user
@app.route("/userJobs")
def userJobs():	

	username = session['username']	

	# get user jobs
	user_jobs_list = models.user_jobs.query.filter(models.user_jobs.status != "complete", models.user_jobs.status != "retired", models.user_jobs.username == username)	

	# return package
	return_package = []

	for job in user_jobs_list:		

		# get job num
		job_num = job.job_num

		# create package
		status_package = {}
		status_package["job_num"] = job_num #this is pulled from SQL table
		
		# get estimated tasks
		job_est_count = redisHandles.r_job_handle.get("job_{job_num}_est_count".format(job_num=job_num))		
		
		# get assigned tasks
		job_assign_count = redisHandles.r_job_handle.get("job_{job_num}_assign_count".format(job_num=job_num))
		if job_assign_count == None:
			job_assign_count = 0
		
		# get completed tasks
		job_complete_count = redisHandles.r_job_handle.get("job_{job_num}_complete_count".format(job_num=job_num))
		if job_complete_count == None:
			job_complete_count = 0

		# compute percentage complete
		if job_est_count != None:
			comp_percent = '{0:.0%}'.format(float(job_complete_count) / float(job_est_count))
		else:
			comp_percent = 'N/A'

		# spooling, works on stable jobHand object
		if job_assign_count > 0 and job_assign_count < job_est_count :
			# print "Job spooling..."
			status_package['job_status'] = "spooling"
			job.status = "spooling"

		# check if pending
		elif job_complete_count == 0:
			# print "Job Pending, waiting for others to complete.  Isn't that polite?"
			status_package['job_status'] = "pending"	
			job.status = "pending"	

		# check if completed
		elif job_complete_count == job_est_count:						
			status_package['job_status'] = "complete"	
			# udpate job status in SQL db here
			job.status = "complete"
			print "Job Complete!  Updated in SQL."

		# else, must be running
		else:
			status_package['job_status'] = "running"	

		# data return 
		response_dict = {
			"job_num":job_num,
			"job_status":status_package['job_status'],
			"assigned_tasks":job_assign_count,
			"completed_tasks":job_complete_count,
			"estimated_tasks":job_est_count,
			"comp_percent":comp_percent
		}

		# return_package[status_package["job_num"]] = response_dict		
		return_package.append(response_dict)

	# commit all changes to SQL db
	db.session.commit()

	# return return_package
	if request.args.get("data","") == "true":		
		json_string = json.dumps(return_package)
		resp = make_response(json_string)
		resp.headers['Content-Type'] = 'application/json'
		return resp
	else:
		return render_template("userJobs.html",username=username,localConfig=localConfig)


# see all user jobs, including completed
@app.route("/userAllJobs")
def userAllJobs():

	username = session['username']

	# get user jobs
	user_jobs_list = models.user_jobs.query.filter(models.user_jobs.username == username)

	# return package
	return_package = []

	for job in user_jobs_list:

		job_package = {}
		job_package['job_num'] = job.job_num		
		job_package['status'] = job.status

		# push to return package
		return_package.append(job_package)
		
	return render_template("userAllJobs.html",username=session['username'],return_package=return_package)


# Details of a given job
@app.route("/jobDetails/<job_num>")
def jobDetails(job_num):
	
	# get number of estimate tasks
	job_task_num = int(redisHandles.r_job_handle.get("job_{job_num}_est_count".format(job_num=job_num)))

	# get parent object
	job_SQL = db.session.query(models.user_jobs).filter(models.user_jobs.job_num == job_num).first()
	print "job celery task id:",job_SQL.celery_task_id

	job_details = jobs.getTaskDetails(job_SQL.celery_task_id)	
	print job_details

	# get tasks
	tasks_package = {}
	tasks_package['SUCCESS'] = []
	tasks_package['PENDING'] = []
	tasks_package['RETRY'] = []
	tasks_package['FAILURE'] = []

	if job_details.children != None:
		for child in job_details.children:
			tasks_package[child.status].append([child.task_id,child.task_name])
		return render_template("jobDetails.html",job_num=job_num,tasks_package=tasks_package)	
	else:
		return render_template("jobDetails.html",job_num=job_num)	

	
# Details of a given task
@app.route("/taskDetails/<task_id>/<job_num>")
def taskDetails(task_id,job_num):
	
	if task_id != "NULL":	
		# async, celery status
		task_async = jobs.getTaskDetails(task_id)
		# fm2 recorded values
		task_returns = redisHandles.r_job_handle.get(task_id).split(",")		
		PID = task_returns[1]	

	else:
		print "We're dealing with a local job, not Celerized"
		PID = "N/A"
		task_async = {
			"status":"N/A",
			"result":"N/A"
		}

	return render_template("taskDetails.html",task_async=task_async,PID=PID)	


# Remove job from SQL, remove tasks from Redis
@app.route("/jobRemove/<job_num>", methods=['POST', 'GET'])
def jobRemove(job_num):	
		
	if request.method == "POST" and request.form['commit'] == "true":
		print "Removing job {job_num}".format(job_num=job_num)
		result = jobs.jobRemove_worker(job_num)
		print result

		return render_template("jobRemove.html",job_num=job_num,result=result)

	return render_template("jobRemove.html",job_num=job_num)


# Remove job from SQL, remove tasks from Redis
@app.route("/jobRetire/<job_num>", methods=['POST', 'GET'])
def jobRetire(job_num):		
	
	result = jobs.jobRetire_worker(job_num)		
	print result

	return redirect("/userJobs")


# Remove job from SQL, remove tasks from Redis
@app.route("/flushPIDLock", methods=['POST', 'GET'])
def flushPIDLock():
	result = redisHandles.r_PIDlock.flushdb()
	print "Result of PID Lock flush:",result
	return render_template("flushPIDLock.html",result=result)




# OBJECT MANAGEMENT
####################################################################################

# View to get 30,000 ft handle one Objects slated to be acted on
@app.route("/objPreview/<PIDnum>", methods=['POST', 'GET'])
@utilities.objects_needed
def objPreview(PIDnum):	

	object_package = {}

	# GET CURRENT OBJECTS	
	PIDlet = jobs.genPIDlet(int(PIDnum))
	if PIDlet == False:
		return utilities.applicationError("PIDnum is out of range or invalid.  Object-at-a-Glance is displeased.")
	PIDlet['pURL'] = "/objPreview/"+str(int(PIDnum)-1)
	PIDlet['nURL'] = "/objPreview/"+str(int(PIDnum)+1)	

	# get handle
	obj_handle = fedora_handle.get_object(PIDlet['cPID'])

	# General Metadata
	solr_params = {'q':utilities.escapeSolrArg(PIDlet['cPID']), 'rows':1}
	solr_results = solr_handle.search(**solr_params)
	solr_package = solr_results.documents[0]
	object_package['solr_package'] = solr_package

	# COMPONENTS
	object_package['components_package'] = []
	riquery = fedora_handle.risearch.spo_search(subject=None, predicate="info:fedora/fedora-system:def/relations-external#isMemberOf", object="info:fedora/"+PIDlet['cPID'])
	for s,p,o in riquery:
		object_package['components_package'].append(s.encode('utf-8'))
	if len(object_package['components_package']) == 0:
		object_package.pop('components_package')		


	# RDF RELATIONSHIPS
	riquery = fedora_handle.risearch.spo_search(subject="info:fedora/"+PIDlet['cPID'], predicate=None, object=None)
	
	# parse
	riquery_filtered = []
	for s,p,o in riquery:	
		riquery_filtered.append((p,o))	
		# optional filtering
		# try:
		# 	if "relations-external" in p or "WSUDOR-Fedora-Relations" in p or "model#" in p:
		# 		riquery_filtered.append((p,o))	
		# except:
		# 	print "Could not parse RDF relationship"
	riquery_filtered.sort()
	object_package['rdf_package'] = riquery_filtered

	
	# DATASTREAMS		
	ds_list = obj_handle.ds_list
	object_package['datastream_package'] = ds_list

	
	# OAI
	OAI_dict = {}	
	#identifer
	try:
		riquery = fedora_handle.risearch.spo_search(subject="info:fedora/"+PIDlet['cPID'], predicate="http://www.openarchives.org/OAI/2.0/itemID", object=None)
		OAI_ID = riquery.objects().next().encode('utf-8')
		OAI_dict['ID'] = OAI_ID
	except:
		print "No OAI Identifier found."
	
	# sets
	OAI_dict['sets'] = []
	try:
		riquery = fedora_handle.risearch.spo_search(subject="info:fedora/"+PIDlet['cPID'], predicate="http://digital.library.wayne.edu/fedora/objects/wayne:WSUDOR-Fedora-Relations/datastreams/RELATIONS/content/isMemberOfOAISet", object=None)
		for each in riquery.objects():
			OAI_dict['sets'].append(each)					
	except:
		print "No OAI sets found."

	object_package['OAI_package'] = OAI_dict
	print object_package['OAI_package']

	# RENDER
	return render_template("objPreview.html",PIDlet=PIDlet,object_package=object_package)	


# PID check for user
@app.route("/PIDmanage")
def PIDmanage():	
	# get username from session
	username = session['username']

	# gen group list	
	user_pid_groups = db.session.query(models.user_pids).filter(models.user_pids.username == username).group_by("group_name")
	group_names = [each.group_name.encode('ascii','ignore') for each in user_pid_groups]	

	# pass the current PIDs to page as list	
	return render_template("PIDManage.html",username=username, group_names=group_names, localConfig=localConfig)


# Select / Deselect / Remove PIDs from user list
@app.route("/PIDmanageAction/<action>", methods=['POST', 'GET'])
def PIDmanageAction(action):	
	# get username from session
	username = session['username']
	print "Current action is:",action

	# if post AND group toggle
	if request.method == 'POST' and action == 'group_toggle':		
		group_name = request.form['group_name']
		db.session.execute("UPDATE user_pids SET status = CASE WHEN status = False THEN True ELSE False END WHERE username = '{username}' AND group_name = '{group_name}';".format(username=username,group_name=group_name))

	# select all
	if action == "s_all":
		print "All PIDs selected..."		
		db.session.query(models.user_pids).filter(models.user_pids.username == username).update({'status': True})
	
	# select none
	if action == "s_none":
		print "All PIDs unselected..."
		db.session.query(models.user_pids).filter(models.user_pids.username == username).update({'status': False})
	
	# select toggle	
	if action == "s_toggle":		
		print "All PIDs toggling..."
		db.session.execute("UPDATE user_pids SET status = CASE WHEN status = False THEN True ELSE False END WHERE username = '{username}';".format(username=username))
	
	# delete selections
	if action == "s_del":
		db.session.query(models.user_pids).filter(models.user_pids.username == username, models.user_pids.status == True).delete()

	# commit changes
	db.session.commit()

	return "Update Complete."

	# pass the current PIDs to page as list	
	return redirect("/PIDmanage")


# small function toggle selection of PIDs
@app.route("/PIDRowUpdate/<id>/<action>/<status>")
def PIDRowUpdate(id,action,status):
	# get username from session
	username = session['username']

	# update single row status
	if action == "update_status":
		# get PID with query
		PID = models.user_pids.query.filter(models.user_pids.id == id)[0]
		# update
		if status == "toggle":
			# where PID.status equals current status in SQL
			if PID.status == False:
				PID.status = True
			elif PID.status == True:
				PID.status = False
		else:
			PID.status = status		

	# delete single row
	if action == "delete":
		# get PID with query
		PID = models.user_pids.query.filter(models.user_pids.id == id)[0]
		db.session.delete(PID)
		print "Deleted PID id#",id,"from SQL database"

	# commit
	db.session.commit()	

	return "PID updated."


# PID selection via Solr
@app.route("/PIDSolr", methods=['POST', 'GET'])
def PIDSolr():	
	'''
	Current Approach: If POST, send results as large array to template, save as JS variable
		- works great so far at 800+ items, but what about 100,000+?
		- documentation says ~ 50,000 is the limit
		- will need to think of a server-side option
	'''
	# get username from session
	username = session['username']

	# get form
	form = forms.solrSearch(request.form)

	# dynamically update fields

	# collection selection
	coll_query = {'q':"rels_hasContentModel:*Collection", 'fl':["id","dc_title"], 'rows':1000}
	coll_results = solr_handle.search(**coll_query)
	coll_docs = coll_results.documents
	form.collection_object.choices = [(each['id'].encode('ascii','ignore'), each['dc_title'][0].encode('ascii','ignore')) for each in coll_docs]
	form.collection_object.choices.insert(0,("","All Collections"))	

	# content model
	cm_query = {'q':'*', 'facet' : 'true', 'facet.field' : 'rels_hasContentModel'}
	cm_results = solr_handle.search(**cm_query)	
	form.content_model.choices = [(each, each.split(":")[-1]) for each in cm_results.facets['facet_fields']['rels_hasContentModel']]
	form.content_model.choices.insert(0,("","All Content Types"))

	# perform search	
	if request.method == 'POST':
		
		# build base with native Solr queries
		query = {'q':form.q.data, 'fq':[form.fq.data], 'fl':[form.fl.data], 'rows':100000}
				
		# Fedora RELS-EXT
		# collection selection
		if form.collection_object.data:			
			print "Collection refinement:",form.collection_object.data						
			escaped_coll = form.collection_object.data.replace(":","\:") 
			query['fq'].append("rels_isMemberOfCollection:info\:fedora/"+escaped_coll)				


		# content model / type selection
		if form.content_model.data:			
			print "Content Model refinement:",form.content_model.data
			escaped_cm = form.content_model.data.replace(":","\:") 
			query['fq'].append("rels_hasContentModel:"+escaped_cm)				

		

		# issue query
		print query
		stime = time.time() 
		q_results = solr_handle.search(**query)
		etime = time.time()
		ttime = (etime - stime) * 1000
		print "Solr Query took:",ttime,"ms"		
		output_dict = {}
		data = []
		stime = time.time()
		for each in q_results.documents:
			try:			
				PID = each['id'].encode('ascii','ignore')
				dc_title = each['dc_title'][0].encode('ascii','ignore')
				data.append([PID,dc_title])
			except:				
				print "Could not render:",each['id'] #unicdoe solr id
		etime = time.time()
		ttime = (etime - stime) * 1000
		print "Solr Munging for DataTables took::",ttime,"ms"		

		output_dict['data'] = data
		json_output = json.dumps(data)

		return render_template("PIDSolr.html",username=username, form=form, q_results=q_results, json_output=json_output, coll_docs=coll_docs)		

	# pass the current PIDs to page as list	
	return render_template("PIDSolr.html",username=username, form=form, coll_docs=coll_docs)


# PID check for user
@app.route("/updatePIDsfromSolr/<update_type>", methods=['POST', 'GET'])
def updatePIDsfromSolr(update_type):	
	# get username from session
	username = session['username']	
	print "Sending PIDs to",username

	# retrieve PIDs
	PIDs = request.form['json_package']
	PIDs = json.loads(PIDs)	

	# get PIDs group_name
	group_name = request.form['group_name'].encode('ascii','ignore')

	# add PIDs to SQL
	if update_type == "add":		
		jobs.sendUserPIDs(username,PIDs,group_name)		
	
	# remove PIDs from SQL
	if update_type == "remove":
		print "removing each PID from SQL..."
		jobs.removeUserPIDs(username,PIDs)
		print "...complete."

	return "Update Complete."


# PID check for user
@app.route("/userPin", methods=['POST', 'GET'])
def userPin():	
	# get username from session
	username = session['username']	

	# get date object
	date_obj = datetime.now()

	# perform search	
	if request.method == 'POST':

		print "generating pin"		

		form_data = request.form
		print form_data

		# check credentials
		user_handle = db.session.query(models.User).filter(models.User.username == form_data['username'],models.User.password == form_data['password']).first()

		if user_handle != None:
			print user_handle

			# create user pin
			user_pin = utilities.genUserPin(form_data['username'])

			return render_template("userPin.html",username=username,date=date_obj, user_pin=user_pin)
		
	# render page
	return render_template("userPin.html",username=username,date=date_obj)
	
# SERVER MANAGEMENT
####################################################################################

# Clear imageServer Cache
@app.route("/imgServerCacheClear")
def imgServerCacheClear():

	# run os command an return results
	results = os.system("rm /tmp/imageServer/*")	
	if results == 0:
		msg = "imageServer Cache successfully cleared."
	else:
		msg = "An error was had: {results}".format(results=results)
		
	return render_template("imgServerCacheClear.html",msg=msg)


# EXPERIMENTAL SERVICES
####################################################################################
# stream bits from Fedora through fm2
@app.route("/strDS/<PID>/<DS>", methods=['POST', 'GET'])
def strDS(PID,DS):
	obj_handle = fedora_handle.get_object(PID)
	obj_ds_handle = obj_handle.getDatastreamObject(DS)

	# chunked, generator
	def stream():
		step = 1024
		pointer = 0
		for chunk in range(0, len(obj_ds_handle.content), step):
			yield obj_ds_handle.content[chunk:chunk+step]

	return Response(stream(), mimetype=obj_ds_handle.mimetype)

	# straight pipe, thinking maybe download first?
	# return Response(obj_ds_handle.content, mimetype=obj_ds_handle.mimetype)	




######################################################
# Catch all - DON'T REMOVE
######################################################
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):    
	return render_template("404.html")













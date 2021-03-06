// likely be removed if moving to prettier tempating
function exportJobStatus(job_package){
	
	var return_string = "Job #"+job_package.job_num+", <strong>"+job_package.job_name+"</strong>: "+job_package.completed_tasks+" / "+job_package.estimated_tasks+" ("+job_package.comp_percent+") - "+job_package.job_status+" - (assigned: "+job_package.assigned_tasks+") - <a href='/jobDetails/"+job_package.job_num+"'>Job Details</a>";
	 
	return return_string;
}

// function to perform polling, requires wait_time variable	
function poll(wait_time, APP_BASE_URL){
	var longPoller = setTimeout(function(){
		url = APP_BASE_URL+"/userJobs?data=true";
		$.ajax({ 
			url: url, 
			dataType:"json",
			success: function(response){

				// iterate through jobs here...
				// this will be drastically improved for jquery bars...
				for (var i=0; i<response.length; i++){
					var job_package = response[i];
					if($("#job_num_" + job_package.job_num).length == 0) {
						//it doesn't exist
						$("#job_list").append("<li id='job_num_"+job_package.job_num+"'>"+exportJobStatus(job_package)+"</li>");	
					}
					else{
						$("#job_num_"+job_package.job_num).html(exportJobStatus(job_package));
					}
					
				}				

				// clear timeOut and set new time if neccessary					
				// wait_time = updateLongPoller(response.job_status,longPoller);

				// the loop
				if (response.job_status != "complete"){
					poll(wait_time,APP_BASE_URL);	
				}
				else{
					console.log("finis!");
				}
			}		
		}); // end ajax
	}, wait_time)		
}

// function to modify polling time if job is spooling or pending
function updateLongPoller(status,longPoller){		
	if (status == "spooling" || status == "pending"){
		console.log("setting new timeout");
		clearTimeout(longPoller);
		return 3000;
	}
	else {
		return 1000;
	}
}
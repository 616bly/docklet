from flask import session, redirect, request
from webViews.view import normalView
from webViews.log import logger
from webViews.checkname import checkname
from webViews.dockletrequest import dockletRequest

class batchJobListView(normalView):
    template_path = "batch/batch_list.html"

    @classmethod
    def get(self):
        masterips = dockletRequest.post_to_all()
        result = dockletRequest.post("/batch/job/list/",{},masterips[0].split("@")[0])
        job_list = result.get("data")
        logger.debug("job_list: %s" % job_list)
        if True:
            return self.render(self.template_path, job_list=job_list)
        else:
            return self.error()

class createBatchJobView(normalView):
    template_path = "batch/batch_create.html"

    @classmethod
    def get(self):
        masterips = dockletRequest.post_to_all()
        images = dockletRequest.post("/image/list/",{},masterips[0].split("@")[0]).get("images")
        if True:
            return self.render(self.template_path, masterips=masterips, images=images)
        else:
            return self.error()

class stateBatchJobView(normalView):
    template_path = "batch/batch_state.html"

    @classmethod
    def get(self):
        if True:
            return self.render(self.template_path)
        else:
            return self.error()

class addBatchJobView(normalView):
    template_path = "batch/batch_list.html"

    @classmethod
    def post(self):
        masterip = self.masterip
        result = dockletRequest.post("/batch/job/add/", self.job_data, masterip)
        if result.get('success', None) == "true":
            return redirect('/batch_jobs/')
        else:
            return self.error()

class outputBatchJobView(normalView):
    template_path = "batch/batch_output.html"
    jobid = ""
    taskid = ""
    vnodeid = ""
    issue = ""

    @classmethod
    def get(self):
        masterips = dockletRequest.post_to_all()
        data = {
            'jobid':self.jobid,
            'taskid':self.taskid,
            'vnodeid':self.vnodeid,
            'issue':self.issue
        }
        result = dockletRequest.post("/batch/job/output/",data,masterips[0].split("@")[0])
        output = result.get("data")
        #logger.debug("job_list: %s" % job_list)
        if result.get('success',"") == "true":
            return self.render(self.template_path, masterip=masterips[0].split("@")[0], jobid=self.jobid,
                               taskid=self.taskid, vnodeid=self.vnodeid, issue=self.issue, output=output)
        else:
            return self.error()

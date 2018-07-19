import threading
import time
import string
import random
import json

import master.monitor

# must import logger after initlogging, ugly
from utils.log import initlogging
initlogging("docklet-taskmgr")
from utils.log import logger

# grpc
from concurrent import futures
import grpc
from protos.rpc_pb2 import Task, TaskMsg, Status, Reply, Parameters, Cluster, Command, Image, Mount, Instance
from protos.rpc_pb2_grpc import MasterServicer, add_MasterServicer_to_server, WorkerStub


class TaskReporter(MasterServicer):

    def __init__(self, taskmgr):
        self.taskmgr = taskmgr

    def report(self, request, context):
        self.taskmgr.on_task_report(request)
        return Reply(status=Reply.ACCEPTED, message='')


class TaskMgr(threading.Thread):

    # load task information from etcd
    # initial a task queue and task schedueler
    # taskmgr: a taskmgr instance
    def __init__(self, nodemgr):
        threading.Thread.__init__(self)
        self.thread_stop = False
        self.jobmgr = None
        self.task_queue = []
        self.heart_beat_timeout = 60 # (s)

        # nodes
        self.nodemgr = nodemgr
        self.cpu_usage = {}
        # self.all_nodes = None
        # self.last_nodes_info_update_time = 0
        # self.nodes_info_update_interval = 30 # (s)


    def run(self):
        self.serve()
        while not self.thread_stop:
            task, instance_id, worker = self.task_scheduler()
            if task is not None and worker is not None:
                self.task_processor(task, instance_id, worker)
            else:
                time.sleep(2)


    def serve(self):
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        add_MasterServicer_to_server(TaskReporter(self), self.server)
        self.server.add_insecure_port('[::]:50051')
        self.server.start()
        logger.info('[taskmgr_rpc] start rpc server')


    def stop(self):
        self.thread_stop = True
        self.server.stop(0)
        logger.info('[taskmgr_rpc] stop rpc server')


    # this method is called when worker send heart-beat rpc request
    def on_task_report(self, report):
        logger.info('[on_task_report] receive task report: id %s-%d, status %d' % (report.taskid, report.instanceid, report.instanceStatus))
        task = get_task(report.taskid)
        if task == None:
            logger.error('[on_task_report] task not found')
            return

        instance = task.instance_list[report.instanceid]
        if instance['token'] != report.token:
            logger.warning('[on_task_report] wrong token')
            return

        instance['status'] = report.instanceStatus

        if report.instanceStatus == Status.RUNNING:
            instance['last_update_time'] = time.time()
        else:
            self.cpu_usage[instance['worker']] -= task.cluster.instance.cpu

        if report.instanceStatus == Status.COMPLETED:
            check_task_completed(task)
        elif report.instanceStatus == Status.FAILED or report.instanceStatus == Status.TIMEOUT:
            if instance['try_count'] > task.maxRetryCount:
                check_task_completed(task)
        else:
            logger.error('[on_task_report] receive report from waiting task')


    def check_task_completed(self, task):
        if len(task.instance_list) < task.instanceCount:
            return
        failed = False
        for instance in task.instance_list:
            if instance['status'] == Status.RUNNING or instance['status'] == Status.WAITING:
                return
            if instance['status'] == Status.FAILED or instance['status'] == Status.TIMEOUT:
                if instance['try_count'] > task.maxRetryCount:
                    failed = True
                else:
                    return
        if self.jobmgr is None:
            logger.error('[check_task_completed] jobmgr is None!')
            return
        if failed:
            # TODO tell jobmgr task failed
            task.status = Status.FAILED
        else:
            # TODO tell jobmgr task completed
            task.status = Status.COMPLETED
        logger.info('task %s completed' % task.id)
        self.task_queue.remove(task)


    def task_processor(self, task, instance_id, worker):
        task.status = Status.RUNNING

        # properties for transaction
        task.instanceid = instance_id
        task.token = ''.join(random.sample(string.ascii_letters + string.digits, 8))

        instance = task.instance_list[instance_id]
        instance['status'] = Status.RUNNING
        instance['last_update_time'] = time.time()
        instance['try_count'] += 1
        instance['token'] = task.token
        instance['worker'] = worker

        self.cpu_usage[worker] += task.cluster.instance.cpu

        try:
            logger.info('[task_processor] processing %s' % task.id)
            channel = grpc.insecure_channel('%s:50052' % worker)
            stub = WorkerStub(channel)
            response = stub.process_task(task)
            if response.status != Reply.ACCEPTED:
                raise Exception(response.message)
        except Exception as e:
            logger.error('[task_processor] rpc error message: %s' % e)
            instance['status'] = Status.FAILED
            instance['try_count'] -= 1


    # return task, worker
    def task_scheduler(self):
        # simple FIFO
        for task in self.task_queue:
            worker = self.find_proper_worker(task)
            if worker is not None:
                # find instance to retry
                for instance, index in enumerate(task.instance_list):
                    if (instance['status'] == Status.FAILED or instance['status'] == Status.TIMEOUT) and instance['try_count'] <= task.maxRetryCount:
                        return task, index, worker
                    elif instance['status'] == Status.RUNNING:
                        if time.time() - instance['last_update_time'] > self.heart_beat_timeout:
                            instance['status'] = Status.FAILED
                            instance['token'] = ''
                            return task, index, worker

                # start new instance
                if len(task.instance_list) < task.instanceCount:
                    instance = {}
                    instance['try_count'] = 0
                    task.instance_list.append(instance)
                    return task, len(task.instance_list) - 1, worker
        return None


    def find_proper_worker(self, task):
        nodes = get_all_nodes()
        if nodes is None or len(nodes) == 0:
            logger.warning('[task_scheduler] running nodes not found')
            return None

        for worker_ip, worker_info in nodes:
            if task.cluster.instance.cpu + get_cpu_usage(worker_ip) > worker_info['cpu']:
                continue
            if task.cluster.instance.memory > worker_info['memory']:
                continue
            if task.cluster.instance.disk > worker_info['disk']:
                continue
            if task.cluster.instance.gpu > worker_info['gpu']:
                continue
            return worker_ip
        return None


    def get_all_nodes(self):
        # cache running nodes
        # if self.all_nodes is not None and time.time() - self.last_nodes_info_update_time < self.nodes_info_update_interval:
        #     return self.all_nodes
        # get running nodes
        node_ips = self.nodemgr.get_nodeips()
        all_nodes = [(node_ip, get_worker_resource_info(node_ip)) for node_ip in node_ips]
        return all_nodes


    def get_worker_resource_info(self, worker_ip):
        fetcher = master.monitor.Fetcher(worker_ip)
        worker_info = fetcher.info
        info = {}
        info['cpu'] = len(worker_info['cpuconfig'])
        info['memory'] = worker_info['meminfo']['free'] / 1024 # (Mb)
        info['disk'] = sum([disk['free'] for disk in worker_info['diskinfo']]) / 1024 / 1024 # (Mb)
        info['gpu'] = 0 # not support yet
        return info


    def get_cpu_usage(self, worker_ip):
        try:
            return self.cpu_usage[worker_ip]
        except:
            self.cpu_usage[worker_ip] = 0
            return 0


    def set_jobmgr(self, jobmgr):
        self.jobmgr = jobmgr


    # user: username
    # task: a json string
    # save the task information into database
    # called when jobmgr assign task to taskmgr
    def add_task(self, username, taskid, json_task):
        # decode json string to object defined in grpc
        json_task = json.loads(json_task)
        task = Task(
            id = taskid,
            username = username,
            instanceCount = json_task['instanceCount'],
            maxRetryCount = json_task['maxRetryCount'],
            timeout = json_task['timeout'],
            parameters = Parameters(
                command = Command(
                    commandLine = json_task['parameters']['command']['commandLine'],
                    packagePath = json_task['parameters']['command']['packagePath'],
                    envVars = json_task['parameters']['command']['envVars']),
                stderrRedirectPath = json_task['parameters']['stderrRedirectPath'],
                stdoutRedirectPath = json_task['parameters']['stdoutRedirectPath']),
            cluster = Cluster(
                image = Image(
                    name = json_task['cluster']['image']['name'],
                    type = json_task['cluster']['image']['type'],
                    owner = json_task['cluster']['image']['owner']),
                instance = Instance(
                    cpu = json_task['cluster']['instance']['cpu'],
                    memory = json_task['cluster']['instance']['memory'],
                    disk = json_task['cluster']['instance']['disk'],
                    gpu = json_task['cluster']['instance']['gpu'])))
        task.cluster.mount = [Mount(localPath=mount['localPath'], remotePath=mount['remotePath'])
                                 for mount in json_task['cluster']['mount']]

        # local properties
        task.status = Status.WAITING
        task.instance_list = []
        self.task_queue.append(task)


    # user: username
    # get the information of a task, including the status, task description and other information
    def get_task(self, taskid):
        for task in self.task_queue:
            if task.id == taskid:
                return task
        return None

# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
import grpc

from protos import rpc_pb2 as rpc__pb2


class MasterStub(object):
  # missing associated documentation comment in .proto file
  pass

  def __init__(self, channel):
    """Constructor.

    Args:
      channel: A grpc.Channel.
    """
    self.report = channel.unary_unary(
        '/Master/report',
        request_serializer=rpc__pb2.ReportMsg.SerializeToString,
        response_deserializer=rpc__pb2.Reply.FromString,
        )


class MasterServicer(object):
  # missing associated documentation comment in .proto file
  pass

  def report(self, request, context):
    # missing associated documentation comment in .proto file
    pass
    context.set_code(grpc.StatusCode.UNIMPLEMENTED)
    context.set_details('Method not implemented!')
    raise NotImplementedError('Method not implemented!')


def add_MasterServicer_to_server(servicer, server):
  rpc_method_handlers = {
      'report': grpc.unary_unary_rpc_method_handler(
          servicer.report,
          request_deserializer=rpc__pb2.ReportMsg.FromString,
          response_serializer=rpc__pb2.Reply.SerializeToString,
      ),
  }
  generic_handler = grpc.method_handlers_generic_handler(
      'Master', rpc_method_handlers)
  server.add_generic_rpc_handlers((generic_handler,))


class WorkerStub(object):
  # missing associated documentation comment in .proto file
  pass

  def __init__(self, channel):
    """Constructor.

    Args:
      channel: A grpc.Channel.
    """
    self.process_task = channel.unary_unary(
        '/Worker/process_task',
        request_serializer=rpc__pb2.TaskInfo.SerializeToString,
        response_deserializer=rpc__pb2.Reply.FromString,
        )
    self.stop_tasks = channel.unary_unary(
        '/Worker/stop_tasks',
        request_serializer=rpc__pb2.ReportMsg.SerializeToString,
        response_deserializer=rpc__pb2.Reply.FromString,
        )


class WorkerServicer(object):
  # missing associated documentation comment in .proto file
  pass

  def process_task(self, request, context):
    # missing associated documentation comment in .proto file
    pass
    context.set_code(grpc.StatusCode.UNIMPLEMENTED)
    context.set_details('Method not implemented!')
    raise NotImplementedError('Method not implemented!')

  def stop_tasks(self, request, context):
    # missing associated documentation comment in .proto file
    pass
    context.set_code(grpc.StatusCode.UNIMPLEMENTED)
    context.set_details('Method not implemented!')
    raise NotImplementedError('Method not implemented!')


def add_WorkerServicer_to_server(servicer, server):
  rpc_method_handlers = {
      'process_task': grpc.unary_unary_rpc_method_handler(
          servicer.process_task,
          request_deserializer=rpc__pb2.TaskInfo.FromString,
          response_serializer=rpc__pb2.Reply.SerializeToString,
      ),
      'stop_tasks': grpc.unary_unary_rpc_method_handler(
          servicer.stop_tasks,
          request_deserializer=rpc__pb2.ReportMsg.FromString,
          response_serializer=rpc__pb2.Reply.SerializeToString,
      ),
  }
  generic_handler = grpc.method_handlers_generic_handler(
      'Worker', rpc_method_handlers)
  server.add_generic_rpc_handlers((generic_handler,))

from cid.drainer import ContainerInstanceDrainer


def handler(event, context):
    ContainerInstanceDrainer(event, context).run()

import logging

logger = logging.getLogger("haproxy")


def get_new_links(docker, haproxy_container):
    labels = haproxy_container.get("Config", {}).get("Labels", {})
    project = labels.get("com.docker.compose.project", "")
    if not project:
        raise Exception("Cannot read compose labels. Are you using docker compose V2?")

    networks = haproxy_container.get("NetworkSettings", {}).get("Networks", {})
    linked_compose_services = _get_linked_compose_services(networks, project)

    links = _calc_links(docker, linked_compose_services, project)
    return links, ["%s_%s" % (project, service) for service in linked_compose_services]


def _calc_links(docker, linked_compose_services, project):
    links = {}
    for _container in docker.containers():
        container_id = _container.get("Id", "")
        container = docker.inspect_container(container_id)
        compose_labels = container.get("Config", {}).get("Labels", {})
        compose_project = compose_labels.get("com.docker.compose.project", "")
        compose_service = compose_labels.get("com.docker.compose.service", "")

        if compose_project == project and compose_service in linked_compose_services:
            service_name = "%s_%s" % (compose_project, compose_service)
            container_name = container.get("Name").lstrip("/")
            container_evvvars = _get_container_envvars(container)
            endpoints = _get_container_endpoints(container, container_name)
            links[container_id] = {"service_name": service_name,
                                   "container_envvars": container_evvvars,
                                   "container_name": container_name,
                                   "endpoints": endpoints,
                                   "compose_service": compose_service,
                                   "compose_project": compose_project}
    return links


def _get_container_endpoints(container, container_name):
    endpoints = {}
    container_endpoints = container.get("Config", {}).get("ExposedPorts", {})
    for k, v in container_endpoints.iteritems():
        if k:
            terms = k.split("/", 1)
            port = terms[0]
            if len(terms) == 2:
                protocol = terms[1]
            else:
                protocol = "tcp"
            if not v:
                v = "%s://%s:%s" % (protocol, container_name, port)
            endpoints[k] = v
    return endpoints


def _get_container_envvars(container):
    container_evvvars = []
    envvars = container.get("Config", {}).get("Env", [])
    for envvar in envvars:
        terms = envvar.split("=", 1)
        container_evvvar = {"key": terms[0]}
        if len(terms) == 2:
            container_evvvar["value"] = terms[1]
        else:
            container_evvvar["value"] = ""
        container_evvvars.append(container_evvvar)
    return container_evvvars


def _get_linked_compose_services(networks, project):
    prefix = "%s_" % project
    prefix_len = len(prefix)

    haproxy_links = []
    for network in networks.itervalues():
        haproxy_links.extend(network.get("Links", []))

    linked_services = []
    for link in haproxy_links:
        terms = link.strip().split(":")
        service = terms[0].strip()
        if service and service.startswith(prefix):
            last = service.rfind("_")
            linked_service = service[prefix_len:last]
            if linked_service not in linked_services:
                linked_services.append(linked_service)
    return linked_services


def get_service_links_str(links):
    return sorted(set([link.get("service_name") for link in links.itervalues()]))


def get_container_links_str(haproxy_links):
    return sorted(set([link.get("container_name") for link in haproxy_links.itervalues()]))
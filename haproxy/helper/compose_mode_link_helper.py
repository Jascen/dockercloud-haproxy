import logging
from haproxy.config import LINKED_SERVICES

logger = logging.getLogger("haproxy")


def get_compose_mode_links(docker, haproxy_container):
    labels = haproxy_container.get("Config", {}).get("Labels", {})
    project = labels.get("com.docker.compose.project", "")
    if not project:
        raise Exception("Cannot read compose labels. Are you using docker compose V2?")

    networks = haproxy_container.get("NetworkSettings", {}).get("Networks", {})
    linked_compose_services = _get_linked_compose_services(networks, project)

    links = _calc_links(docker, linked_compose_services, project)
    return links, set(["%s_%s" % (project, service) for service in linked_compose_services])


def get_additional_links(docker, additional_services):
    links = {}
    services = set()
    for additional_service in additional_services.split(","):
        terms = additional_service.strip().split(":")
        if len(terms) == 2:
            project = terms[0]
            service = terms[1]
            link = _calc_links(docker, [service], project)
            if link:
                links.update(link)
                services.add("%s_%s" % (project, service))
            else:
                logger.info("Cannot find the additional service: %s" % additional_service.strip())
    return links, services


def _find_container_networks_ids(container, networks_data):
    ids = []
    for network in networks_data:
        if container['Id'] in network['Containers'].keys():
            ids.append(network['Id'])
    return ids


def _calc_links(docker, linked_compose_services, project):
    links = {}
    for _container in docker.containers():
        container_id = _container.get("Id", "")
        container = docker.inspect_container(container_id)
        compose_labels = container.get("Config", {}).get("Labels", {})
        compose_project = compose_labels.get("com.docker.compose.project", "")
        compose_service = compose_labels.get("com.docker.compose.service", "")
                
        linked_service_names = {}
        for x in str(LINKED_SERVICES).strip().split(";"):
            if not x.strip():
                break
            
            service_values = x.strip().split(":")
            service_name = "%s" % service_values[0]
            if len(service_values) == 2:
                linked_service_names[service_name] = {y: {} for y in service_values[1].strip().split(",") if y}
            else:
                linked_service_names[service_name] = {}
            
        if compose_project == project and compose_service in linked_compose_services:
            service_name = "%s_%s" % (compose_project, compose_service)
            container_name = container.get("Name").lstrip("/")
            container_evvvars = get_container_envvars(container)
            explicit_endpoints = linked_service_names.get(compose_service, {})
            endpoints = get_container_endpoints(container, container_name, explicit_endpoints)
            links[container_id] = {"service_name": service_name,
                                   "container_envvars": container_evvvars,
                                   "container_name": container_name,
                                   "endpoints": endpoints,
                                   "compose_service": compose_service,
                                   "compose_project": compose_project}
    return links


def get_container_endpoints(container, container_name, explicit_endpoints):
    endpoints = {}
    if not explicit_endpoints:
        explicit_endpoints = container.get("Config", {}).get("ExposedPorts", {})

    for k, v in explicit_endpoints.iteritems():
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

def get_container_envvars(container):
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
        network_links = network.get("Links", [])
        if network_links:
            haproxy_links.extend(network_links)

    linked_service_names = []
    if LINKED_SERVICES:
        for x in str(LINKED_SERVICES).strip().split(";"):
            if not x.strip():
                break
            service_values = x.strip().split(":")
            if service_values:
                linked_service_names.append("%s" % (service_values[0]))

    linked_services = []
    for link in haproxy_links:
        terms = link.strip().split(":")
        service = terms[0].strip()    
        if service and service.startswith(prefix):
            last = service.rfind("_")
            linked_service = service[prefix_len:last]
            if linked_service_names and linked_service not in linked_service_names:
                continue
            if linked_service not in linked_services:                
                linked_services.append(linked_service)
    return linked_services


def get_service_links_str(links):
    return sorted(set([link.get("service_name") for link in links.itervalues()]))


def get_container_links_str(haproxy_links):
    return sorted(set([link.get("container_name") for link in haproxy_links.itervalues()]))

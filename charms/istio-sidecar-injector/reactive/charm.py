from pathlib import Path
from subprocess import run

from charms import layer
from charms.reactive import set_flag, clear_flag, when, when_not


@when('charm.started')
def charm_ready():
    layer.status.active('')


@when('layer.docker-resource.oci-image.changed')
def update_image():
    clear_flag('charm.started')


@when('layer.docker-resource.oci-image.available')
@when_not('charm.started')
def start_charm():
    layer.status.maintenance('configuring container')

    image_info = layer.docker_resource.get_info('oci-image')

    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:4096",
            "-keyout",
            "key.pem",
            "-out",
            "cert.pem",
            "-days",
            "365",
            "-subj",
            "/CN=localhost",
            "-nodes",
        ],
        check=True,
    )

    layer.caas_base.pod_spec_set(
        {
            'containers': [
                {
                    'name': 'sidecar-injector-webhook',
                    'args': [
                        '--caCertFile=/etc/istio/certs/root-cert.pem',
                        '--tlsCertFile=/etc/istio/certs/cert-chain.pem',
                        '--tlsKeyFile=/etc/istio/certs/key.pem',
                        '--injectConfig=/etc/istio/inject/config',
                        '--meshConfig=/etc/istio/config/mesh',
                        '--healthCheckInterval=2s',
                        '--healthCheckFile=/health',
                    ],
                    'imageDetails': {
                        'imagePath': image_info.registry_path,
                        'username': image_info.username,
                        'password': image_info.password,
                    },
                    'livenessProbe': {
                        'exec': {
                            'command': [
                                '/usr/local/bin/sidecar-injector',
                                'probe',
                                '--probe-path=/health',
                                '--interval=4s',
                            ]
                        },
                        'initialDelaySeconds': 4,
                        'periodSeconds': 4,
                    },
                    'ports': [
                        {'name': 'validation', 'containerPort': 443},
                        {'name': 'monitoring', 'containerPort': 15014},
                        {'name': 'grpc-mcp', 'containerPort': 9901},
                    ],
                    'readinessProbe': {
                        'exec': {
                            'command': [
                                '/usr/local/bin/sidecar-injector',
                                'probe',
                                '--probe-path=/health',
                                '--interval=4s',
                            ]
                        },
                        'initialDelaySeconds': 4,
                        'periodSeconds': 4,
                    },
                    'files': [
                        {
                            'name': 'config-volume',
                            'mountPath': '/etc/istio/config',
                            'files': {
                                'mesh': Path('files/mesh.yaml').read_text(),
                                'meshNetworks': 'networks: {}',
                            },
                        },
                        {
                            'name': 'certs',
                            'mountPath': '/etc/istio/certs',
                            'files': {
                                'root-cert.pem': Path('cert.pem').read_text(),
                                'cert-chain.pem': Path('cert.pem').read_text(),
                                'key.pem': Path('key.pem').read_text(),
                            },
                        },
                        {
                            'name': 'inject-config',
                            'mountPath': '/etc/istio/inject',
                            'files': {'config': Path('config.yaml').read_text()},
                        },
                    ],
                }
            ]
        }
    )

    layer.status.maintenance('creating container')
    set_flag('charm.started')

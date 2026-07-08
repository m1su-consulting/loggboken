from app.parsers.kubectl_describe import parse_describe_pods_text

POD_WITH_SIDECAR_AND_INIT_CONTAINER = """\
Name:             api-7f9c9d-abc12
Namespace:        payments
Priority:         0
Service Account:  default
Node:             node-1/10.0.0.5
Start Time:       Mon, 01 Jun 2026 10:00:00 +0000
Labels:           app=api
                  pod-template-hash=7f9c9d
Annotations:      kubectl.kubernetes.io/default-container: api
Status:           Running
IP:               10.0.1.23
IPs:
  IP:  10.0.1.23
Controlled By:  ReplicaSet/api-7f9c9d
Init Containers:
  wait-for-db:
    Container ID:  containerd://aaa111
    Image:         registry.example.com/payments/wait-for-db:1.0.0
    Image ID:      registry.example.com/payments/wait-for-db@sha256:aaa
    Port:          <none>
    Host Port:     <none>
    State:         Terminated
      Reason:      Completed
      Exit Code:   0
    Ready:         True
    Restart Count: 0
    Environment:   <none>
    Mounts:        <none>
Containers:
  api:
    Container ID:   containerd://bbb222
    Image:          registry.example.com/payments/api:1.4.2
    Image ID:       registry.example.com/payments/api@sha256:bbb
    Port:           8080/TCP
    Host Port:      0/TCP
    State:          Running
      Started:      Mon, 01 Jun 2026 10:00:05 +0000
    Ready:          True
    Restart Count:  0
    Environment:    <none>
    Mounts:         <none>
  istio-proxy:
    Container ID:   containerd://ccc333
    Image:          istio/proxyv2:1.20.0
    Image ID:       istio/proxyv2@sha256:ccc
    Port:           15090/TCP
    Host Port:      0/TCP
    State:          Running
      Started:      Mon, 01 Jun 2026 10:00:06 +0000
    Ready:          True
    Restart Count:  0
    Environment:    <none>
    Mounts:         <none>
Conditions:
  Type              Status
  Initialized       True
  Ready             True
  ContainersReady   True
  PodScheduled      True
Volumes:
  kube-api-access-xxxx:
    Type:  Projected
QoS Class:       Burstable
Node-Selectors:  <none>
Tolerations:     node.kubernetes.io/not-ready:NoExecute op=Exists for 300s
Events:
  Type    Reason     Age   From               Message
  ----    ------     ----  ----               -------
  Normal  Scheduled  5m    default-scheduler  Successfully assigned payments/api-7f9c9d-abc12 to node-1
  Normal  Pulled     5m    kubelet            Container image already present on machine
  Normal  Created    5m    kubelet            Created container wait-for-db
  Normal  Started    5m    kubelet            Started container wait-for-db
"""

POD_WITHOUT_ANNOTATIONS = """\
Name:             worker-5d7f8-m3q99
Namespace:        payments
Priority:         0
Node:             node-2/10.0.0.6
Start Time:       Mon, 01 Jun 2026 10:05:00 +0000
Labels:           app=worker
Status:           Running
IP:               10.0.1.30
Containers:
  worker:
    Container ID:   containerd://ddd444
    Image:          registry.example.com/payments/worker:1.0.0
    Port:           <none>
    Host Port:      <none>
    State:          Running
      Started:      Mon, 01 Jun 2026 10:05:05 +0000
    Ready:          True
    Restart Count:  0
    Environment:    <none>
    Mounts:         <none>
Conditions:
  Type              Status
  Initialized       True
QoS Class:        BestEffort
Events:            <none>
"""


def test_parses_pod_name_annotation_containers_and_init_containers() -> None:
    pods = parse_describe_pods_text(POD_WITH_SIDECAR_AND_INIT_CONTAINER)

    assert len(pods) == 1
    pod = pods[0]
    assert pod["metadata"]["name"] == "api-7f9c9d-abc12"
    assert pod["metadata"]["annotations"] == {
        "kubectl.kubernetes.io/default-container": "api"
    }
    assert pod["spec"]["containers"] == [
        {"name": "api", "image": "registry.example.com/payments/api:1.4.2"},
        {"name": "istio-proxy", "image": "istio/proxyv2:1.20.0"},
    ]
    assert pod["spec"]["initContainers"] == [
        {"name": "wait-for-db", "image": "registry.example.com/payments/wait-for-db:1.0.0"}
    ]
    assert pod["spec"]["nodeName"] == "node-1"


def test_pod_without_annotations_or_init_containers() -> None:
    pods = parse_describe_pods_text(POD_WITHOUT_ANNOTATIONS)

    assert len(pods) == 1
    pod = pods[0]
    assert pod["metadata"]["name"] == "worker-5d7f8-m3q99"
    assert pod["metadata"]["annotations"] == {}
    assert pod["spec"]["containers"] == [
        {"name": "worker", "image": "registry.example.com/payments/worker:1.0.0"}
    ]
    assert pod["spec"]["initContainers"] == []
    assert pod["spec"]["nodeName"] == "node-2"


def test_unscheduled_pod_has_no_node_name() -> None:
    text = """\
Name:             pending-pod-abc12
Namespace:        payments
Node:             <none>
Containers:
  app:
    Image:          registry.example.com/payments/app:1.0.0
"""
    pods = parse_describe_pods_text(text)

    assert len(pods) == 1
    assert "nodeName" not in pods[0]["spec"]


def test_multiple_pods_in_one_describe_output_are_split_correctly() -> None:
    combined = POD_WITH_SIDECAR_AND_INIT_CONTAINER + "\n" + POD_WITHOUT_ANNOTATIONS

    pods = parse_describe_pods_text(combined)

    assert len(pods) == 2
    assert pods[0]["metadata"]["name"] == "api-7f9c9d-abc12"
    assert pods[1]["metadata"]["name"] == "worker-5d7f8-m3q99"


def test_empty_text_returns_no_pods() -> None:
    assert parse_describe_pods_text("") == []
    assert parse_describe_pods_text("not a kubectl describe output at all") == []

# test_alerting.py
# TO RUN : pytest tests/test_alerting.py -v
from edge_monitor.alerting import check_thresholds
from edge_monitor.config import Thresholds


# Scenario 1: everything normal -- no alerts expected
def test_no_alerts_when_below_threshold():
    metrics = {
        "cpu": {"percent": 20.0},
        "memory": {"percent": 30.0},
        "disk": {"percent": 40.0},
        "gpu": None
    }
    thresholds = Thresholds()
    result = check_thresholds(metrics, thresholds)
    print("\nresult:", result)
    assert result == []


# Scenario 2: CPU breaches -- one alert expected
def test_cpu_alert_when_above_threshold():
    metrics = {
        "cpu": {"percent": 95.0},
        "memory": {"percent": 30.0},
        "disk": {"percent": 40.0},
        "gpu": None
    }
    thresholds = Thresholds()
    result = check_thresholds(metrics, thresholds)
    print("\nresult:", result)
    assert len(result) == 1
    assert "CPU" in result[0]


# Scenario 3: GPU is None -- no crash expected
def test_no_crash_when_gpu_is_none():
    metrics = {
        "cpu": {"percent": 20.0},
        "memory": {"percent": 30.0},
        "disk": {"percent": 40.0},
        "gpu": None
    }
    thresholds = Thresholds()
    result = check_thresholds(metrics, thresholds)
    print("\nresult:", result)
    assert result == []


# Scenario 4: CPU and Memory both breach -- two alerts expected
def test_multiple_alerts_when_cpu_and_memory_high():
    metrics = {
        "cpu": {"percent": 95.0},
        "memory": {"percent": 92.0},
        "disk": {"percent": 40.0},
        "gpu": None
    }
    thresholds = Thresholds()
    result = check_thresholds(metrics, thresholds)
    print("\nresult:", result)
    assert len(result) == 2
    assert "CPU" in result[0]
    assert "Memory" in result[1]


# Scenario 5: GPU breaches -- two GPU alerts expected
def test_gpu_alerts_when_high():
    metrics = {
        "cpu": {"percent": 20.0},
        "memory": {"percent": 30.0},
        "disk": {"percent": 40.0},
        "gpu": {
            "utilization_percent": 99,
            "temperature_c": 88
        }
    }
    thresholds = Thresholds()
    result = check_thresholds(metrics, thresholds)
    print("\nresult:", result)
    assert len(result) == 2
    assert "GPU" in result[0]
    assert "GPU" in result[1]


# Scenario 6: disk breaches -- one alert expected
def test_disk_alert_when_high():
    metrics = {
        "cpu": {"percent": 20.0},
        "memory": {"percent": 30.0},
        "disk": {"percent": 95.0},
        "gpu": None
    }
    thresholds = Thresholds()
    result = check_thresholds(metrics, thresholds)
    print("\nresult:", result)
    assert len(result) == 1
    assert "Disk" in result[0]


# Scenario 7: custom threshold -- breach at lower value
def test_custom_threshold():
    metrics = {
        "cpu": {"percent": 50.0},
        "memory": {"percent": 30.0},
        "disk": {"percent": 40.0},
        "gpu": None
    }
    thresholds = Thresholds(cpu_percent=40.0)  # lower threshold
    result = check_thresholds(metrics, thresholds)
    print("\nresult:", result)
    assert len(result) == 1
    assert "CPU" in result[0]
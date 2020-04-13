# universal-tsdb
A Universal Time-Series Database Python Client (InfluxDB, Warp10, ...)

[![Build Status](https://travis-ci.com/gmasse/universal-tsdb.svg?branch=master)](https://travis-ci.com/gmasse/universal-tsdb)
[![codecov](https://codecov.io/gh/gmasse/universal-tsdb/branch/master/graph/badge.svg)](https://codecov.io/gh/gmasse/universal-tsdb)
[![PyPI](https://img.shields.io/pypi/v/universal-tsdb?color=brightgreen)](https://pypi.org/project/universal-tsdb/)
![PyPI - Status](https://img.shields.io/pypi/status/universal-tsdb)


## Introduction
This project aims to abstract your Time-Series backend, keeping your code as agnostic as possible.

Some examples:
 - proof of concept
 - early stages of development (when you are not sure which plateform you should use)
 - ETL (Extract-Transform-Load), for the load step

:warning: The current code only offer INGESTING functions (writing points to a backend).


## Quickstart

### Installation
```bash
$ pip install universal-tsdb
```
```python
>>> from universal_tsdb import Client, Ingester
>>> backend = Client('influx', 'http://localhost:8086', database='test')
>>> series = Ingester(backend)
>>> series.append(1585934895000, measurement='data', field1=42.0)
>>> series.payload()
'data field1=42.0 1585934895000000000\n'
>>> series.commit()
```

### InfluxDB
```python
from universal_tsdb import Client, Ingester

backend = Client('influx', 'http://localhost:8086', database='metrics',
                 backend_username='user', backend_password='passwd')
series = Ingester(backend)
series.append(1585934895000, measurement='mes', field1=42.0)
series.append(1585934896000, measurement='mes', tags={'tag1':'value1'}, field1=43.4, field2='value')
series.commit()
```
The code above will generate a data payload based on InfluxDB line protocol
and send it via a HTTP(S) request.
```
POST /write?db=metrics&u=user&p=passwd HTTP/1.1
Host: localhost:8086

mes field1=42.0 1585934895000000000
mes,tag1=value1 field1=43.4 field2="value" 1585934896000000000
```

### Warp10
```python
from universal_tsdb import Client, Ingester

backend = Client('warp10', 'http://localhost/api/v0', token='WRITING_TOKEN_ABCDEF0123456789')
series = Ingester(backend)
series.append(1585934895000, field1=42.0)
series.append(1585934896000, tags={'tag1':'value1'}, field1=43.4, field2='value')
series.commit()
```
The code above will generate a data payload based on Warp10 GTS format
and send it via a HTTP(S) request.
```
POST /api/v0/update HTTP/1.1
Host: localhost
X-Warp10-Token: WRITING_TOKEN_ABCDEF0123456789

1585934895000000// field1{} 42.0
1585934896000000// field1{tag1=value1} 42.0
1585934896000000// field2{tag1=value1} 'value'
```


## Advanced Usage

### Batch processing
When you have a large volume of data to send, you may want to split in several HTTP requests.
In 'batch'-mode, the library commit (send) the data automatically:
```python
backend = Client('influx', 'http://localhost:8086', database='metrics')
series = Ingester(backend, batch=10)
for i in range(0..26):
    series.append(field=i)
series.commit() # final commit to save the last 6 values
```
```
Commit#1 Sent 10 new series (total: 10) in 0.02 s @ 2000.0 series/s (total execution: 0.13 s)
Commit#2 Sent 10 new series (total: 20) in 0.02 s @ 2000.0 series/s (total execution: 0.15 s)
Commit#3 Sent 6 new series (total: 26) in 0.01 s @ 2000.0 series/s (total execution: 0.17 s)
REPORT: 3 commits (3 successes), 26 series, 26 values in 0.17 s @ 2000.0 values/s",
```

### Omitting Timestamp
If you omit timestamp, the library uses the function `time.time()`
to generate a UTC Epoch Time. Precision is system dependent.

### Measurement in Warp10
InfluxDB measurement does not exist in Warp10.
The library emulates measurement by prefixing the Warp10 classname:
```python
backend = Client('warp10', token='WRITING_TOKEN_ABCDEF0123456789')
series = Ingester(backend)
series.append(1585934895000, measurement='mes', field1=42.0) 
series.commit()
```
```
1585934896000000// mes.field1{} 42.0 
```


## Todo
- [ ] API documentation
- [ ] Examples
- [ ] Data query/fetch functions
- [ ] Refactoring of backend specific code (inherited classes?)
- [ ] Time-Series Line protocol optimization
- [ ] Gzip/deflate HTTP compression
- [ ] Additional tests

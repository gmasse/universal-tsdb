# vim: ai:ts=4:sw=4:sts=4:expandtab:textwidth=100:colorcolumn=+0

"""A Universal Time-Series Database Python Client"""

import time
import urllib.parse
import logging
import requests
from .exceptions import MaxErrorsException

logging.getLogger(__name__).addHandler(logging.NullHandler())

class Client:
    """Multi-backend abstraction class"""

    DEFAULT_TIMEOUT = 30

    def __init__(self, protocol, url, database=None, http_username=None, http_password=None,
                 backend_username=None, backend_password=None, token=None, timeout=DEFAULT_TIMEOUT):
        self.protocol = protocol
        self._url = url
        self._database = database
        self._http_auth = (http_username, http_password)
        self._backend_auth = (backend_username, backend_password)
        self._token = token
        self._timeout = timeout

        # Sanitary check
        if self.protocol == 'warp10':
            pass
        elif self.protocol == 'influx':
            if not database:
                raise ValueError("Influx database missing")
        else:
            raise ValueError("Unsupported backend: {}".format(self.protocol))

        # HTTP Session
        self._session = requests.Session()
        if http_username or http_password:
            self._session.auth = self._http_auth
        if token:
            if self.protocol == 'warp10':
                self._session.headers.update({'X-Warp10-Token': self._token})
            else:
                raise ValueError("Token authentification not supported for {} backend"
                                 .format(self.protocol))
        logging.debug("%s client instanciated", self.protocol)

    def prepare_request(self, payload):
        """Prepare a HTTP Request
        Return: Requests.PreparedRequest"""
        if self.protocol == 'warp10':
            # https://www.warp10.io/content/03_Documentation/03_Interacting_with_Warp_10/03_Ingesting_data/01_Ingress
            # $ curl -H 'X-Warp10-Token: TOKEN_WRITE' -H 'Transfer-Encoding: chunked' \
            #  -T METRICS_FILE 'https://HOST:PORT/api/v0/update'
            req = requests.Request(
                method='POST',
                url=self._url + '/update',
                data=payload
            )
            return self._session.prepare_request(req)
        if self.protocol == 'influx':
            # https://docs.influxdata.com/influxdb/v1.7/tools/api/#write-http-endpoint
            # $ curl -i -XPOST "http://localhost:8086/write?db=mydb" \
            #  --data-binary 'mymeas,mytag=1 myfield=90 1463683075000000000'
            req = requests.Request(
                method='POST',
                url=self._url + '/write',
                params={'db':self._database, 'u':self._backend_auth[0], 'p':self._backend_auth[1]},
                data=payload
            )
            return self._session.prepare_request(req)
        return None

    def send(self, prepped):
        """Send to backend"""
        try:
            response = self._session.send(prepped, verify=True, timeout=(3.05, self._timeout))
            response.raise_for_status()
        except Exception as err:
            logging.debug("Response:")
            logging.debug(self._dump_response(response))
            logging.debug("-----------------------------------------")
            logging.debug("Request:")
            logging.debug(self._dump_request(prepped))
            raise err

    @staticmethod
    def _dump_request(req):
        """HTTP request dumper
        https://stackoverflow.com/a/23816211"""
        return '{}\n{}\r\n{}\r\n\r\n{}'.format(
            '----------HTTP REQUEST----------',
            req.method + ' ' + req.url,
            '\r\n'.join('{}: {}'.format(k, v) for k, v in req.headers.items()),
            req.body,
        )

    @staticmethod
    def _dump_response(resp):
        """HTTP response dumper"""
        return '{}\n{}\r\n{}\r\n\r\n{}'.format(
            '----------HTTP RESPONSE----------',
            str(resp.status_code) + ' ' + resp.url,
            '\r\n'.join('{}: {}'.format(k, v) for k, v in resp.headers.items()),
            resp.content,
        )


class Ingester:
    """Ingester class"""

    INFLUX_DEFAULT_MEASUREMENT_NAME = 'data'
    MAX_ERRORS = 3

    def __init__(self, client, batch=0):
        self.client = client
        self._batch = batch
        self._payload = ""
        self._length = 0
        self._report = {'series': 0, 'values': 0, 'successes': 0, 'commits': 0,
                        'time': 0, '_timer_main': time.monotonic(), '_timer_batch': None}
        self._successive_fails = 0
        logging.debug("ingester instanciated")

    def __del__(self):
        if self._batch > 0 and self._length > 0:
            logging.warning(("Destroying instance with non-flushed payload. "
                             "Always purge() or commit() before destruction."))
        if self._batch > 0 and self._report['time'] > 0:
            logging.info("REPORT: %d commits (%d successes), %d series, %d values "
                         "in %.2f s @ %.1f values/s",
                         self._report['commits'], self._report['successes'],
                         self._report['series'], self._report['values'],
                         self._report['time'], self._report['values']/self._report['time'])
        else:
            logging.info("REPORT: %d commits (%d successes), %d series, %d values",
                         self._report['commits'], self._report['successes'],
                         self._report['series'], self._report['values'])

    def _esc(self, value):
        if self.client.protocol == 'warp10':
            return urllib.parse.quote(str(value), safe='')
        if self.client.protocol == 'influx':
            value = str(value).replace(
                "\\", "\\\\"
                ).replace(
                    " ", "\\ "
                    ).replace(
                        ",", "\\,"
                        ).replace(
                            "=", "\\="
                            ).replace(
                                "\n", "\\n"
                                ).replace(
                                    "'", "\\'"
                                    ).replace(
                                        "\"", "\\\""
                                        )
            if value.endswith('\\'):
                value += ' '
            return value
        return None

    def payload(self):
        """Return current payload"""
        return self._payload

    def length(self):
        """Return number of series included in the current payload.
        A Series can have multiple field=value couples"""
        return self._length

    def _append_warp10(self, timestamp, tags_statement="", measurement=None, **kwargs):
        """Translate to Warp10 GTS series"""
        for key, val in kwargs.items():
            if measurement is not None:
                key = measurement+'.'+key
            if isinstance(val, str):
                val = "'"+self._esc(val)+"'"
            elif isinstance(val, bool):
                if val:
                    val = 'T'
                else:
                    val = 'F'
            elif isinstance(val, int):
                pass
            elif isinstance(val, float):
                pass
            else:
                raise ValueError("Invalid or unsupported value (key: {})".format(key))

            micro_ts = timestamp * 1000 # in µs
            self._payload += "{}// {}{{{}}} {}\n".format(micro_ts, self._esc(key),
                                                         tags_statement, val)
            self._length += 1
            self._report['values'] += 1
            self._report['series'] += 1
#TODO(gmasse): support condensed format with continuation lines
# https://www.warp10.io/content/03_Documentation/03_Interacting_with_Warp_10/03_Ingesting_data/02_GTS_input_format#continuation-lines

    def _append_influx(self, timestamp, tags_statement="", measurement=None, **kwargs):
        # https://docs.influxdata.com/influxdb/v1.7/write_protocols/line_protocol_reference/
        fields_statement = ''
        separator = ''
        for key, val in kwargs.items():
            if isinstance(val, str):
                val = "\""+self._esc(val)+"\""
            elif isinstance(val, bool):
                if val:
                    val = 'T'
                else:
                    val = 'F'
            elif isinstance(val, int):
                val = str(val)+'i'
            elif isinstance(val, float):
                pass
            else:
                raise ValueError("Invalid or unsupported value (key: {})".format(key))
            fields_statement = "{}{}{!s}={!s}".format(fields_statement, separator,
                                                      self._esc(key), val)
            separator = ','
            self._report['values'] += 1

        if measurement is None or measurement == '':
            measurement = self.INFLUX_DEFAULT_MEASUREMENT_NAME
        if tags_statement:
            tags_statement = ','+tags_statement
        nano_ts = timestamp * 1000000 # in ns
        self._payload += "{}{} {} {}\n".format(measurement, tags_statement,
                                               fields_statement, nano_ts)
        self._length += 1
        self._report['series'] += 1

    def append(self, timestamp=None, tags=None, measurement=None, **kwargs):
        """Write a new point"""
        if self._batch > 0:
            if self._report['_timer_batch'] is None:
                self._report['_timer_batch'] = time.monotonic()
        if timestamp is None:
            timestamp = int(time.time()*1000) # UTC Epoch in ms
        elif not isinstance(timestamp, int):
            raise ValueError('Invalid timestamp')
        if tags is not None and not isinstance(tags, dict):
            raise ValueError('Invalid tags format')
        if measurement is not None and not isinstance(measurement, str):
            raise ValueError('Invalid measurement')

        tags_statement = ''
        if tags is not None:
            separator = ''
            for (key, val) in tags.items():
                tags_statement = "{}{}{!s}={!s}".format(tags_statement, separator,
                                                        self._esc(key), self._esc(val))
                separator = ','

        if self.client.protocol == 'warp10':
            self._append_warp10(timestamp, tags_statement, measurement, **kwargs)
        elif self.client.protocol == 'influx':
            self._append_influx(timestamp, tags_statement, measurement, **kwargs)

        if self._batch > 0 and self._length >= self._batch:
            self.commit()

    def purge(self):
        """Flusgh payload"""
        self._payload = ""
        self._length = 0
        self._report['_timer_batch'] = None

    def commit(self):
        """Send previous added point to backend"""
        if self._length > 0:
            self._report['commits'] += 1
            logging.info("Sending HTTP request")
            logging.debug("Data: %s", self.payload().rstrip())
            prepped = self.client.prepare_request(self.payload())
            try:
                self.client.send(prepped)
            except requests.exceptions.RequestException as err:
                # In batch mode, even if we encouter HTTP error,
                # we keep the payload until we reach
                # MAX-ERRORS successive failures
                if self._batch > 0:
                    self._successive_fails += 1
                    logging.warning("Attempt#%d/%d HTTP Error: %s",
                                    self._successive_fails, self.MAX_ERRORS, err)
                    if self._successive_fails >= self.MAX_ERRORS:
                        logging.error("Commit aborted after %d unsuccessful attempts",
                                      self._successive_fails)
                        self._report['time'] = time.monotonic() - self._report['_timer_main']
                        raise MaxErrorsException
                else:
                    raise err
            except Exception as err:
                raise err
            else:
                self._successive_fails = 0
                if self._batch > 0:
                    if self._report['_timer_batch'] is None:
                        batch_duration = 0
                        batch_freq = 0
                    else:
                        batch_duration = time.monotonic() - self._report['_timer_batch']
                        batch_freq = self._length/batch_duration
                self._report['successes'] += 1
                self._report['time'] = time.monotonic() - self._report['_timer_main']
                if self._batch > 0:
                    logging.info("Commit#%d Sent %d new series (total: %d) in %.2f s "
                                 "@ %.1f series/s (total execution: %.2f s)",
                                 self._report['commits'], self.length(),
                                 self._report['series'], batch_duration,
                                 batch_freq, self._report['time'])
                else:
                    logging.info("Commit#%d Sent %d new series (total: %d)",
                                 self._report['commits'], self.length(), self._report['series'])
                self.purge()

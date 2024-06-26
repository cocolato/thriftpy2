# -*- coding: utf-8 -*-

from __future__ import absolute_import

import os
import multiprocessing
import socket
import sys
import time
import uuid

import pytest

import thriftpy2

thriftpy2.install_import_hook()  # noqa

from thriftpy2.http import make_server, make_client, client_context, THttpHeaderFactory  # noqa
from thriftpy2.thrift import TApplicationException  # noqa

addressbook = thriftpy2.load(os.path.join(os.path.dirname(__file__),
                                          "addressbook.thrift"))


if sys.platform == "win32":
    pytest.skip("requires fork", allow_module_level=True)


class Dispatcher():
    def __init__(self):
        self.ab = addressbook.AddressBook()
        self.ab.people = {}

    def ping(self):
        return True

    def hello(self, name):
        return "hello " + name

    def add(self, person):
        self.ab.people[person.name] = person
        return True

    def remove(self, name):
        try:
            self.ab.people.pop(name)
            return True
        except KeyError:
            raise addressbook.PersonNotExistsError(
                "{} not exists".format(name))

    def get(self, name):
        try:
            return self.ab.people[name]
        except KeyError:
            raise addressbook.PersonNotExistsError(
                "{} not exists".format(name))

    def book(self):
        return self.ab

    def get_phonenumbers(self, name, count):
        p = [self.ab.people[name].phones[0]] if name in self.ab.people else []
        return p * count

    def get_phones(self, name):
        phone_numbers = self.ab.people[name].phones
        return dict((p.type, p.number) for p in phone_numbers)

    def sleep(self, ms):
        time.sleep(ms / 1000.0)
        return True


class CustomHeaderFactory(THttpHeaderFactory):
    def get_headers(self):
        return {"X-REQUEST-ID": str(uuid.uuid4())}


@pytest.fixture(scope="module")
def server(request):
    server = make_server(addressbook.AddressBookService, Dispatcher(),
                         host="127.0.0.1", port=6080)
    ps = multiprocessing.Process(target=server.serve)
    ps.start()

    time.sleep(0.1)

    def fin():
        if ps.is_alive():
            ps.terminate()
    request.addfinalizer(fin)


@pytest.fixture(scope="module")
def person():
    phone1 = addressbook.PhoneNumber()
    phone1.type = addressbook.PhoneType.MOBILE
    phone1.number = '555-1212'
    phone2 = addressbook.PhoneNumber()
    phone2.type = addressbook.PhoneType.HOME
    phone2.number = '555-1234'

    # empty struct
    phone3 = addressbook.PhoneNumber()

    alice = addressbook.Person()
    alice.name = "Alice"
    alice.phones = [phone1, phone2, phone3]
    alice.created_at = int(time.time())

    return alice


def client(timeout=3000):
    return client_context(addressbook.AddressBookService,
                          host="127.0.0.1", port=6080, timeout=timeout)


def client_context_with_url(timeout=3000):
    return client_context(addressbook.AddressBookService,
                          url="http://127.0.0.1:6080", timeout=timeout)


def client_context_with_malformed_path(timeout=3000):
    return client_context(addressbook.AddressBookService, host="127.0.0.1",
                          port=6080, path="foo", timeout=timeout)


def client_with_url(timeout=3000):
    return make_client(addressbook.AddressBookService,
                       url="http://127.0.0.1:6080", timeout=timeout)


def client_without_url(timeout=3000):
    return make_client(addressbook.AddressBookService, host="127.0.0.1",
                       port=6080, path="/foo", timeout=timeout)


@pytest.fixture
def client_with_malformed_path(timeout=3000):
    return make_client(addressbook.AddressBookService, host="127.0.0.1",
                       port=6080, path="foo", timeout=timeout)


def client_context_with_header_factory(timeout=3000):
    return client_context(addressbook.AddressBookService,
                          url="http://127.0.0.1:6080",
                          timeout=timeout,
                          http_header_factory=THttpHeaderFactory())


def client_context_with_custom_header_factory(timeout=3000):
    return client_context(addressbook.AddressBookService,
                          url="http://127.0.0.1:6080",
                          timeout=timeout,
                          http_header_factory=CustomHeaderFactory())


def client_with_header_factory(timeout=3000):
    return make_client(addressbook.AddressBookService,
                       url="http://127.0.0.1:6080",
                       timeout=timeout,
                       http_header_factory=THttpHeaderFactory(
                           {"X-REQUEST-ID": str(uuid.uuid4())}))


def client_with_custom_header_factory(timeout=3000):
    return make_client(addressbook.AddressBookService,
                       url="http://127.0.0.1:6080",
                       timeout=timeout,
                       http_header_factory=CustomHeaderFactory())


def test_client_context(server):
    with client() as c1, client_context_with_url() as c2,\
         client_context_with_malformed_path() as c3:
        assert c1.hello("world") == c2.hello("world") == c3.hello("world")


def test_clients(server):
    with client() as c1:
        c2 = client_with_url()
        assert c1.hello("world") == c2.hello("world")
        c2.close()


def test_clients_without_url(server):
    c = client_without_url()
    assert c.hello("world") == "hello world"


def test_client_with_malformed_path(client_with_malformed_path):
    assert client_with_malformed_path.hello("world") == "hello world"


def test_client_context_with_header_factory(server):
    with client_context_with_header_factory() as c:
        assert c.hello("world") == "hello world"


def test_client_context_custom_with_header_factory(server):
    with client_context_with_custom_header_factory() as c:
        assert c.hello("world") == "hello world"


def test_client_with_header_factory(server):
    c = client_with_header_factory()
    assert c.hello("world") == "hello world"
    c.close()


def test_client_with_custom_header_factory(server):
    c = client_with_custom_header_factory()
    assert c.hello("world") == "hello world"
    c.close()


def test_void_api(server):
    with client() as c:
        assert c.ping() is None


def test_string_api(server):
    with client() as c:
        assert c.hello("world") == "hello world"


def test_required_argument(server):
    with client() as c:
        with pytest.raises(TApplicationException):
            c.hello()

        assert c.hello(name="") == "hello "


def test_huge_res(server):
    with client() as c:
        big_str = "world" * 100000
        assert c.hello(big_str) == "hello " + big_str


def test_tstruct_req(person):
    with client() as c:
        assert c.add(person) is True


def test_tstruct_res(person):
    with client() as c:
        assert person == c.get("Alice")


def test_complex_tstruct():
    with client() as c:
        assert len(c.get_phonenumbers("Alice", 0)) == 0
        assert len(c.get_phonenumbers("Alice", 1000)) == 1000


def test_exception():
    with pytest.raises(addressbook.PersonNotExistsError):
        with client() as c:
            c.remove("Bob")


def test_client_timeout():
    with pytest.raises(socket.timeout):
        with client(timeout=200) as c:
            c.sleep(400)

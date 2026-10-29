from django.test import TestCase
from django.test import RequestFactory
#from django.urls import Resolver404

from django.conf import settings
from django.core.handlers.wsgi import WSGIHandler

#from myapp.wsgi import my_wsgi_app
# since praktomat.wsgi is not a module, we simulate that it is a module.

def my_wsgi_loader() -> WSGIHandler:
    from os.path import join
    MODULE_NAME = "praktomat"
    MODULE_PATH = join(settings.PRAKTOMAT_PATH,"wsgi","praktomat.wsgi")
    #print ("DEBUG: MODULE_PATH=",MODULE_PATH)
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader(MODULE_NAME, MODULE_PATH)
    spec = importlib.util.spec_from_loader(MODULE_NAME, loader)
    if spec is None:
        raise ImportError(f"Could not load WSGI module from {MODULE_PATH}")
    mymodule = importlib.util.module_from_spec(spec)
    loader.exec_module(mymodule)
    assert isinstance(mymodule.application, WSGIHandler)
    return mymodule.application


class PraktomatMyWsgiTest(TestCase):
    def setUp(self) -> None:
        pass

    def tearDown(self) -> None:
        pass

    def test_praktomat_WSGIHandler_createable(self) -> None:
        application=my_wsgi_loader()  # returns a WSGIHandler
        self.assertIsInstance(application, WSGIHandler, msg="%s : not a WSGIHandler created" % str(self))
        response=application.get_response(RequestFactory().get('/'))
        self.assertEqual(response.status_code , 301 , msg="%s : WSGIHandler : Status was %s != 301 \n %s" %(str(self),response.status_code,str(response)) )
        location = response.get('Location')
        assert location is not None
        self.assertIn("tasks", location , msg="%s : WSGIHandler response : Forward was wrong \n %s" %(str(self),str(response)) )

    def test_praktomat_favicon_from_root(self) -> None:
        application=my_wsgi_loader()  # returns a WSGIHandler
        self.assertIsInstance(application, WSGIHandler, msg="%s : not a WSGIHandler created" % str(self))
        response=application.get_response(RequestFactory().get('/favicon.ico'))
        self.assertEqual(response.status_code , 301 , msg="%s : WSGIHandler : Status was %s != 301 \n %s" %(str(self),response.status_code,str(response)) )
        location = response.get('Location')
        assert location is not None
        self.assertIn("/static/favicon.ico", location , msg="%s : WSGIHandler response : Forward was wrong \n %s" %(str(self),str(response)) )

    def test_praktomat_favicon_from_app(self) -> None:
        application=my_wsgi_loader()  # returns a WSGIHandler
        self.assertIsInstance(application, WSGIHandler, msg="%s : not a WSGIHandler created" % str(self))
        response=application.get_response(RequestFactory().get('/tasks/favicon.ico'))
        self.assertEqual(response.status_code , 301 , msg="%s : WSGIHandler : Status was %s != 301 \n %s" %(str(self),response.status_code,str(response)) )
        location = response.get('Location')
        assert location is not None
        self.assertIn("/static/favicon.ico", location , msg="%s : WSGIHandler response : Forward was wrong \n %s" %(str(self),str(response)) )

## If you want to use the following test case, than you have to install django_webtest and webtest.
#from webtest import TestApp
#from django_webtest import WebTest
#class PraktomatWsgiTest(WebTest):
    #def setUp(self):
        #pass

    #def tearDown(self):
        #pass

    #def test_wsgi_root(self):
        #res = self.app.get('/')
        #self.assertEqual(res.status_int , 301 , msg="%s : Running WSGI : Status was %s != 301 \n %s" %(str(self),res.status_int,str(res)) )
        #self.assertIn("tasks", res.headers['Location'] , msg="%s : WSGI response : Forward was wrong \n %s" %(str(self),str(res)) )
        #self.assertTrue(True)

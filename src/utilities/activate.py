import logging
import os

from django.core.exceptions import ObjectDoesNotExist

from accounts.models import User

logger = logging.getLogger(__name__)


def activate(matfilename: str | bytes | os.PathLike[str] | os.PathLike[bytes] | int) -> None:
    with open(matfilename) as f:
        matnummers = f.readlines()
        for matnummer in [int(nr) for nr in matnummers]:
            # print "ImportingMatnummer: %d\t" % matnummer
            try:
                user = User.objects.get(mat_number=matnummer)
                user.is_active = True
                user.save()
            except ObjectDoesNotExist:
                logger.warning("User with matriculation number %d was not found.", matnummer)

"""Config común de los tests.

Los módulos de las Lambdas crean el recurso de DynamoDB en el import, así que
boto3 necesita una región (y unas credenciales cualquiera) antes de importarlos.
Nada de esto llama a AWS: los tests inyectan tablas y clientes falsos.
"""

import os

os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

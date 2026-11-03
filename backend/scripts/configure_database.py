"""Write local development connection settings without putting passwords in argv."""

import argparse
from getpass import getpass
from pathlib import Path

from dotenv import dotenv_values, set_key
from sqlalchemy.engine import URL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', default='192.168.1.217')
    parser.add_argument('--port', type=int, default=1433)
    parser.add_argument('--database', default='OKR')
    parser.add_argument('--test-database', default='OKR_test')
    parser.add_argument('--username', default='sa')
    parser.add_argument('--trust-server-certificate', action='store_true',
                        help='Development only: encrypt traffic without validating the server certificate')
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / '.env'
    if dotenv_values(path).get('OKR_ENV', 'development') != 'development':
        parser.error('This helper only configures a development environment')
    if not args.test_database.lower().endswith('_test'):
        parser.error('Test database name must end in _test')
    password = getpass('SQL login password (hidden): ')
    if not password:
        parser.error('Password cannot be empty')
    for key, database in [('OKR_DATABASE_URL', args.database), ('OKR_TEST_DATABASE_URL', args.test_database)]:
        url = URL.create('mssql+pyodbc', username=args.username, password=password,
                         host=args.server, port=args.port, database=database,
                         query={'driver': 'ODBC Driver 18 for SQL Server', 'Encrypt': 'yes',
                                'TrustServerCertificate': 'yes' if args.trust_server_certificate else 'no'})
        set_key(path, key, url.render_as_string(hide_password=False))
    print('Saved local backend/.env settings. No database objects were changed.')
    print('The file contains credentials; keep it local and restrict access to it.')


if __name__ == '__main__':
    main()

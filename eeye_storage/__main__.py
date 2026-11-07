import argparse
from .receiver import receive_session


def main():
    parser=argparse.ArgumentParser(description='Save an E-Eye session to this computer and verify every file.')
    commands=parser.add_subparsers(dest='command',required=True)
    receiver=commands.add_parser('receive')
    receiver.add_argument('--url',required=True)
    receiver.add_argument('--session',required=True)
    receiver.add_argument('--destination',required=True)
    receiver.add_argument('--device-label')
    receiver.add_argument('--release',action='store_true',help='Explicitly remove verified exported originals from the Pi after saving.')
    args=parser.parse_args()
    try:
        result=receive_session(args.url,args.session,args.destination,args.device_label,args.release)
    except Exception as error:
        parser.exit(1,'Transfer not completed: '+str(error)+'\nPi files were not automatically discarded.\n')
    print('Saved and verified: '+result['path'])
    print('Pi originals released.' if result['pi_files_released'] else 'Pi originals retained. This verified file is not a second backup.')


if __name__=='__main__': main()

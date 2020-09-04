REPORT_NAME     = 'system.domain.name'  # Name of the monitored HBlink system
CONFIG_INC      = True                  # Include FNE stats
FNEMON_IP       = '127.0.0.1'           # FNE's IP Address
FNEMON_PORT     = 4321                  # FNE's TCP reporting socket
FREQUENCY       = 10                    # Frequency to push updates to web clients
WEB_SERVER_PORT = 8080                  # Has to be above 1024 if you're not running as root

HTACCESS_USER   = ''                    # HTTP Access Username
HTACCESS_PASS   = ''                    # HTTP Access Password

ACTIVITY_LOG    = './activity_log.log'  # Remote Activity Log
PRIMARY_MASTER  = ''                    # Name of the primary master to allow remote commands for

# Full path to the DVM RCON tool
DVM_CMD_TOOL    = '/opt/dvmfne/monitor/dvmcmd'

# Files and stuff for loading alias files for mapping numbers to names
PATH            = './'                          # MUST END IN '/'
FILE_RELOAD     = 7                             # Number of days before we reload DMR-MARC database files

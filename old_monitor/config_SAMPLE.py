REPORT_NAME     = 'system.domain.name'  # Name of the monitored HBlink system
FNEMON_IP       = '127.0.0.1'           # FNE's IP Address
FNEMON_PORT     = 4321                  # FNE's TCP reporting socket
FREQUENCY       = 10                    # Frequency to push updates to web clients
ACT_FREQUENCY   = 10                    # Frequency to push activity updates to web clients
WEB_SERVER_PORT = 8080                  # Has to be above 1024 if you're not running as root

HTACCESS_USER   = ''                    # HTTP Access Username
HTACCESS_PASS   = ''                    # HTTP Access Password

ACTIVITY_LOG    = './activity_log.log'  # Remote Activity Log

# Full path to the DVM RCON tool
DVM_CMD_TOOL    = '/opt/dvmfne/monitor/dvmcmd'

# Files and stuff for loading alias files for mapping numbers to names
PATH            = './'                          # MUST END IN '/'
LOG_PATH        = './'                          # MUST END IN '/'

#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <getopt.h>


#include "daemon.h"
#include "smacros.h"
#include "ServiceContext.h"

// ---- gsoap ----
#include "DeviceBinding.nsmap"
#include "soapDeviceBindingService.h"
#include "soapMediaBindingService.h"
#include "soapPTZBindingService.h"

// MK3 PTZ (ServicePTZ.cpp)
void        ptz_init(void);
int         ptz_mcu_info_cli(const char* mode, int watch_ms);
const char* ptz_build_info(void);





static const char *help_str =
        " Daemon name:  " DAEMON_NAME        "\n"
        " Daemon  ver:  " DAEMON_VERSION_STR "\n\n"
#ifdef  DEBUG
        " Build  mode:  debug\n"
#else
        " Build  mode:  release\n"
#endif
        " Build  date:  " __DATE__ "\n"
        " Build  time:  " __TIME__ "\n"
#if  COMMIT_ISDIRTY == 0
        " Build  hash:  "  COMMIT_HASH "\n\n"
#else
        " Build  hash:  *" COMMIT_HASH "\n\n"
#endif
        "Options:                      description:\n\n"
        "       --no_chdir             Don't change the directory to '/'\n"
        "       --no_fork              Don't do fork\n"
        "       --no_close             Don't close standart IO files\n"
        "       --pid_file     [value] Set pid file name\n"
        "       --log_file     [value] Set log file name\n\n"
        "       --port         [value] Set socket port for Services   (default = 1000)\n"
        "       --user         [value] Set user name for Services     (default = admin)\n"
        "       --password     [value] Set user password for Services (default = admin)\n"
        "       --model        [value] Set model device for Services  (default = Model)\n"
        "       --scope        [value] Set scope for Services         (default don't set)\n"
        "       --ifs          [value] Set Net interfaces for work    (default don't set)\n"
        "       --tz_format    [value] Set Time Zone Format           (default = 0)\n"
        "       --hardware_id  [value] Set Hardware ID of device      (default = HardwareID)\n"
        "       --serial_num   [value] Set Serial number of device    (default = SerialNumber)\n"
        "       --firmware_ver [value] Set firmware version of device (default = FirmwareVersion)\n"
        "       --manufacturer [value] Set manufacturer for Services  (default = Manufacturer)\n\n"
        "       --name         [value] Set Name for Profile Media Services\n"
        "       --width        [value] Set Width for Profile Media Services\n"
        "       --height       [value] Set Height for Profile Media Services\n"
        "       --url          [value] Set URL (or template URL) for Profile Media Services\n"
        "       --snapurl      [value] Set URL (or template URL) for Snapshot\n"
        "                              in template mode %s will be changed to IP of interface (see opt ifs)\n"
        "       --type         [value] Set Type for Profile Media Services (JPEG|MPEG4|H264)\n"
        "                              It is also a sign of the end of the profile parameters\n\n"
        "       --ptz                  Enable PTZ support\n"
        "       --move_left    [value] Set process to call for PTZ pan left movement\n"
        "       --move_right   [value] Set process to call for PTZ pan right movement\n"
        "       --move_up      [value] Set process to call for PTZ tilt up movement\n"
        "       --move_down    [value] Set process to call for PTZ tilt down movement\n"
        "       --move_stop    [value] Set process to call for PTZ stop movement\n"
        "       --move_preset  [value] Set process to call for PTZ goto preset movement\n\n"
        "       --mcu-info[=full]      Show live motor angles + firmware/state summary and exit\n"
        "                              (=full adds the firmware settings dump)\n"
        "       --mcu-watch[=sec]      Same as --mcu-info, refreshed every sec (default 1). Ctrl+C to quit\n\n"
        "  -v,  --version              Display daemon version\n"
        "  -h,  --help                 Display this help\n\n";




// indexes for long_opt function
namespace LongOpts
{
    enum
    {
        version = 'v',
        help    = 'h',

        //daemon options
        no_chdir = 1,
        no_fork,
        no_close,
        pid_file,
        log_file,

        //ONVIF Service options (context)
        port,
        user,
        password,
        manufacturer,
        model,
        firmware_ver,
        serial_num,
        hardware_id,
        scope,
        ifs,
        tz_format,

        //Media Profile for ONVIF Media Service
        name,
        width,
        height,
        url,
        snapurl,
        type,

        //PTZ Profile for ONVIF PTZ Service
        ptz,
        move_left,
        move_right,
        move_up,
        move_down,
        move_stop,
        move_preset,

        //MK3
        mcu_info,
        mcu_watch
    };
}



static const char *short_opts = "hv";


static const struct option long_opts[] =
{
    { "version",      no_argument,       NULL, LongOpts::version       },
    { "help",         no_argument,       NULL, LongOpts::help          },

    //daemon options
    { "no_chdir",     no_argument,       NULL, LongOpts::no_chdir      },
    { "no_fork",      no_argument,       NULL, LongOpts::no_fork       },
    { "no_close",     no_argument,       NULL, LongOpts::no_close      },
    { "pid_file",     required_argument, NULL, LongOpts::pid_file      },
    { "log_file",     required_argument, NULL, LongOpts::log_file      },

    //ONVIF Service options (context)
    { "port",         required_argument, NULL, LongOpts::port          },
    { "user",         required_argument, NULL, LongOpts::user          },
    { "password",     required_argument, NULL, LongOpts::password      },
    { "manufacturer", required_argument, NULL, LongOpts::manufacturer  },
    { "model",        required_argument, NULL, LongOpts::model         },
    { "firmware_ver", required_argument, NULL, LongOpts::firmware_ver  },
    { "serial_num",   required_argument, NULL, LongOpts::serial_num    },
    { "hardware_id",  required_argument, NULL, LongOpts::hardware_id   },
    { "scope",        required_argument, NULL, LongOpts::scope         },
    { "ifs",          required_argument, NULL, LongOpts::ifs           },
    { "tz_format",    required_argument, NULL, LongOpts::tz_format     },

    //Media Profile for ONVIF Media Service
    { "name",          required_argument, NULL, LongOpts::name         },
    { "width",         required_argument, NULL, LongOpts::width        },
    { "height",        required_argument, NULL, LongOpts::height       },
    { "url",           required_argument, NULL, LongOpts::url          },
    { "snapurl",       required_argument, NULL, LongOpts::snapurl      },
    { "type",          required_argument, NULL, LongOpts::type         },

    //PTZ Profile for ONVIF PTZ Service
    { "ptz",           no_argument,       NULL, LongOpts::ptz          },
    { "move_left",     required_argument, NULL, LongOpts::move_left    },
    { "move_right",    required_argument, NULL, LongOpts::move_right   },
    { "move_up",       required_argument, NULL, LongOpts::move_up      },
    { "move_down",     required_argument, NULL, LongOpts::move_down    },
    { "move_stop",     required_argument, NULL, LongOpts::move_stop    },
    { "move_preset",   required_argument, NULL, LongOpts::move_preset  },
    { "mcu-info",      optional_argument, NULL, LongOpts::mcu_info     },
    { "mcu-watch",     optional_argument, NULL, LongOpts::mcu_watch    },

    { NULL,           no_argument,       NULL,  0                      }
};





#define FOREACH_SERVICE(APPLY, soap)                    \
        APPLY(DeviceBindingService, soap)               \
        APPLY(MediaBindingService, soap)                \
        APPLY(PTZBindingService, soap)                  \


/*
 * If you need support for other services,
 * add the desired option to the macro FOREACH_SERVICE.
 *
 * Note: Do not forget to add the gsoap binding class for the service,
 * and the implementation methods for it, like for DeviceBindingService



        APPLY(ImagingBindingService, soap)               \
        APPLY(PTZBindingService, soap)                   \
        APPLY(RecordingBindingService, soap)             \
        APPLY(ReplayBindingService, soap)                \
        APPLY(SearchBindingService, soap)                \
        APPLY(ReceiverBindingService, soap)              \
        APPLY(DisplayBindingService, soap)               \
        APPLY(EventBindingService, soap)                 \
        APPLY(PullPointSubscriptionBindingService, soap) \
        APPLY(NotificationProducerBindingService, soap)  \
        APPLY(SubscriptionManagerBindingService, soap)   \
*/


#define DECLARE_SERVICE(service, soap) service service ## _inst(soap);

#define DISPATCH_SERVICE(service, soap)                                  \
                else if (service ## _inst.dispatch() != SOAP_NO_METHOD) {\
                    soap_send_fault(soap);                               \
                    soap_stream_fault(soap, std::cerr);                  \
                }




static struct soap *soap;

ServiceContext service_ctx;





void daemon_exit_handler(int sig)
{
    //Here we release resources

    UNUSED(sig);
    soap_destroy(soap); // delete managed C++ objects
    soap_end(soap);     // delete managed memory
    soap_free(soap);    // free the context


    unlink(daemon_info.pid_file);


    exit(EXIT_SUCCESS); // good job (we interrupted (finished) main loop)
}



void init_signals(void)
{
    set_sig_handler(SIGINT,  daemon_exit_handler); //for Ctlr-C in terminal for debug (in debug mode)
    set_sig_handler(SIGTERM, daemon_exit_handler);

    set_sig_handler(SIGCHLD, SIG_IGN); // ignore child
    set_sig_handler(SIGTSTP, SIG_IGN); // ignore tty signals
    set_sig_handler(SIGTTOU, SIG_IGN);
    set_sig_handler(SIGTTIN, SIG_IGN);
    set_sig_handler(SIGHUP,  SIG_IGN);
}



void processing_cmd(int argc, char *argv[])
{
    int opt;

    StreamProfile  profile;


    while( (opt = getopt_long(argc, argv, short_opts, long_opts, NULL)) != -1 )
    {
        switch( opt )
        {

            case LongOpts::help:
                        puts(help_str);
                        exit_if_not_daemonized(EXIT_SUCCESS);
                        break;

            case LongOpts::version:
                        puts(DAEMON_NAME "  version  " DAEMON_VERSION_STR);
                        printf("MK3 build: %s\n\n", ptz_build_info());
                        fflush(stdout);
                        exit_if_not_daemonized(EXIT_SUCCESS);
                        break;


                 //daemon options
            case LongOpts::no_chdir:
                        daemon_info.no_chdir = 1;
                        break;

            case LongOpts::no_fork:
                        daemon_info.no_fork = 1;
                        break;

            case LongOpts::no_close:
                        daemon_info.no_close_stdio = 1;
                        break;

            case LongOpts::pid_file:
                        daemon_info.pid_file = optarg;
                        break;

            case LongOpts::log_file:
                        daemon_info.log_file = optarg;
                        break;


            //ONVIF Service options (context)
            case LongOpts::port:
                        service_ctx.port = atoi(optarg);
                        break;

            case LongOpts::user:
                        service_ctx.user = optarg;
                        break;

            case LongOpts::password:
                        service_ctx.password = optarg;
                        break;

            case LongOpts::manufacturer:
                        service_ctx.manufacturer = optarg;
                        break;

            case LongOpts::model:
                        service_ctx.model = optarg;
                        break;

            case LongOpts::firmware_ver:
                        service_ctx.firmware_version = optarg;
                        break;

            case LongOpts::serial_num:
                        service_ctx.serial_number = optarg;
                        break;

            case LongOpts::hardware_id:
                        service_ctx.hardware_id = optarg;
                        break;

            case LongOpts::scope:
                        service_ctx.scopes.push_back(optarg);
                        break;

            case LongOpts::ifs:
                        service_ctx.eth_ifs.push_back(Eth_Dev_Param());

                        if( service_ctx.eth_ifs.back().open(optarg) != 0 )
                            daemon_error_exit("Can't open ethernet interface: %s - %m\n", optarg);

                        break;

            case LongOpts::tz_format:
                        if( !service_ctx.set_tz_format(optarg) )
                            daemon_error_exit("Can't set tz_format: %s\n", service_ctx.get_cstr_err());

                        break;


            //Media Profile for ONVIF Media Service
            case LongOpts::name:
                        if( !profile.set_name(optarg) )
                            daemon_error_exit("Can't set name for Profile: %s\n", profile.get_cstr_err());

                        break;


            case LongOpts::width:
                        if( !profile.set_width(optarg) )
                            daemon_error_exit("Can't set width for Profile: %s\n", profile.get_cstr_err());

                        break;


            case LongOpts::height:
                        if( !profile.set_height(optarg) )
                            daemon_error_exit("Can't set height for Profile: %s\n", profile.get_cstr_err());

                        break;


            case LongOpts::url:
                        if( !profile.set_url(optarg) )
                            daemon_error_exit("Can't set URL for Profile: %s\n", profile.get_cstr_err());

                        break;


            case LongOpts::snapurl:
                        if( !profile.set_snapurl(optarg) )
                            daemon_error_exit("Can't set URL for Snapshot: %s\n", profile.get_cstr_err());

                        break;


            case LongOpts::type:
                        if( !profile.set_type(optarg) )
                            daemon_error_exit("Can't set type for Profile: %s\n", profile.get_cstr_err());

                        if( !service_ctx.add_profile(profile) )
                            daemon_error_exit("Can't add Profile: %s\n", service_ctx.get_cstr_err());

                        profile.clear(); //now we can add new profile (just uses one variable)

                        break;


            //PTZ Profile for ONVIF PTZ Service
            case LongOpts::ptz:
                        service_ctx.get_ptz_node()->enable = true;
                        break;


            case LongOpts::move_left:
                        if( !service_ctx.get_ptz_node()->set_move_left(optarg) )
                            daemon_error_exit("Can't set process for pan left movement: %s\n", service_ctx.get_ptz_node()->get_cstr_err());

                        break;


            case LongOpts::move_right:
                        if( !service_ctx.get_ptz_node()->set_move_right(optarg) )
                            daemon_error_exit("Can't set process for pan right movement: %s\n", service_ctx.get_ptz_node()->get_cstr_err());

                        break;


            case LongOpts::move_up:
                        if( !service_ctx.get_ptz_node()->set_move_up(optarg) )
                            daemon_error_exit("Can't set process for tilt up movement: %s\n", service_ctx.get_ptz_node()->get_cstr_err());

                        break;


            case LongOpts::move_down:
                        if( !service_ctx.get_ptz_node()->set_move_down(optarg) )
                            daemon_error_exit("Can't set process for tilt down movement: %s\n", service_ctx.get_ptz_node()->get_cstr_err());

                        break;


            case LongOpts::move_stop:
                        if( !service_ctx.get_ptz_node()->set_move_stop(optarg) )
                            daemon_error_exit("Can't set process for stop movement: %s\n", service_ctx.get_ptz_node()->get_cstr_err());

                        break;


            case LongOpts::mcu_info:
                        exit(ptz_mcu_info_cli(optarg, 0));
                        break;

            case LongOpts::mcu_watch:
                        {
                            double sec = optarg ? atof(optarg) : 1.0;
                            if( sec < 0.2 ) sec = 0.2;
                            exit(ptz_mcu_info_cli(NULL, (int)(sec * 1000)));
                        }
                        break;

            case LongOpts::move_preset:
                        if( !service_ctx.get_ptz_node()->set_move_preset(optarg) )
                            daemon_error_exit("Can't set process for goto preset movement: %s\n", service_ctx.get_ptz_node()->get_cstr_err());

                        break;


            default:
                        puts("for more detail see help\n\n");
                        exit_if_not_daemonized(EXIT_FAILURE);
                        break;
        }
    }
}



void check_service_ctx(void)
{
    if(service_ctx.eth_ifs.empty())
        daemon_error_exit("Error: not set no one ehternet interface more details see opt --ifs\n");


    if(service_ctx.scopes.empty())
        daemon_error_exit("Error: not set scopes more details see opt --scope\n");


    if(service_ctx.get_profiles().empty())
        daemon_error_exit("Error: not set no one profile more details see --help\n");
}



// MK3: WS-Security 헤더 허용 (2026-11-05)
// ONVIF Device Manager·NVR 은 계정을 wsse:Security 헤더(mustUnderstand="1")로 보낸다.
// 이 빌드는 WSSE 플러그인 없이 만들어서 gSOAP 이 그 헤더를 모르고 MustUnderstand fault 로 모든 요청을 거부했다.
// wsse:Security 만 '이해한 것으로' 넘기고, 계정은 아래 mk3_authorize 가 확인한다 (2단계).
// 그 밖의 모르는 mustUnderstand 헤더는 지금처럼 fault, mustUnderstand 아닌 모르는 요소는 지금처럼 무시.
static bool is_wsse_security(struct soap *soap, const char *tag)
{
    const char *local = strchr(tag, ':');
    local = local ? local + 1 : tag;
    if(strcmp(local, "Security") != 0)
        return false;

    const char *ns = soap_current_namespace_tag(soap, tag);
    return ns && strstr(ns, "secext") != NULL;   // OASIS wss 2004/01 ...-secext-1.0.xsd, 구 2002/07 secext
}



static int mk3_fignore(struct soap *soap, const char *tag)
{
    if(!soap->mustUnderstand)
        return SOAP_OK;                          // 예전과 같음: 모르는 요소는 건너뜀

    if(soap->part == SOAP_IN_HEADER && is_wsse_security(soap, tag))
        return SOAP_OK;                          // 내용은 mk3_authorize 가 받은 원문에서 읽는다

    return SOAP_MUSTUNDERSTAND;                  // 예전과 같음
}



// ===== MK3: ONVIF 계정 확인 (2026-11-05, 2단계) =====
// 장비 밖에서 온 요청은 wsse:UsernameToken 의 admin + 비밀번호를 확인한다 (PasswordDigest / PasswordText).
// 기준은 영상(edge stream_auth)과 같다: 웹에서 비밀번호를 정했으면 그것만, 아직이면 장비 시리얼(DEVICE_ID 끝).
//  - edge 는 비밀번호를 sha256("DEVICE_ID:비밀번호") 로만 저장 -> Digest 확인에는 원문이 필요해
//    edge 가 비밀번호를 바꿀 때 ONVIF_AUTH_FILE(root 600)에 원문을 같이 쓴다. 원문은 해시와 맞을 때만 쓴다(옛 값 무시).
//    원문이 없으면 PasswordText 만 해시로 확인 가능, Digest 는 거부 + 로그 안내.
//  - 장비 안(127.x) 요청, 로그인 전 조회(PRE_AUTH: GetSystemDateAndTime 등)는 계정 없이 허용
//  - 비밀번호 5번 틀리면 그 IP 60초 잠금, 잠긴 뒤로도 틀릴 때마다 다시 잠금 (edge 와 같은 규칙, 카운터는 따로)
//  - 비상용: ONVIF_AUTH_OFF_FILE 이 있으면 확인 안 함 (v1.0 과 같음)
#include <openssl/sha.h>
#include <openssl/crypto.h>
#include <map>
#include <string>
#include <fstream>
#include <sstream>
#include <time.h>

static const char *ONVIF_AUTH_FILE     = "/var/lib/onvif_srvd/onvif_auth";      // 웹 비밀번호 원문 (edge 가 씀)
static const char *ONVIF_AUTH_OFF_FILE = "/var/lib/onvif_srvd/onvif_auth_off";  // 있으면 확인 끔
static const char *EDGE_AUTH_FILE      = "/home/ptz/edge/.device_auth";         // edge 웹 비밀번호 해시
static const char *DEVICE_ID_FILE      = "/var/lib/onvif_srvd/device_id";
static const char *ONVIF_USER          = "admin";
static const int    AUTH_MAX_FAILS     = 5;
static const int    AUTH_LOCK_SEC      = 60;

static size_t (*g_orig_frecv)(struct soap*, char*, size_t) = NULL;
static std::string g_rx;                         // 이번 요청 원문 (앞부분 64KB)

static size_t mk3_frecv(struct soap *soap, char *buf, size_t len)
{
    size_t n = g_orig_frecv(soap, buf, len);
    if(n > 0 && g_rx.size() < 65536)
        g_rx.append(buf, n < 65536 - g_rx.size() ? n : 65536 - g_rx.size());
    return n;
}



static std::string read_file(const char *path)
{
    std::ifstream f(path, std::ios::binary);
    if(!f.is_open()) return std::string();
    std::stringstream ss; ss << f.rdbuf();
    return ss.str();
}

static std::string trim_nl(std::string s)
{
    while(!s.empty() && (s.back() == '\n' || s.back() == '\r' || s.back() == ' ' || s.back() == '\t')) s.pop_back();
    size_t i = 0;
    while(i < s.size() && (s[i] == ' ' || s[i] == '\t')) ++i;
    return s.substr(i);
}

static std::string sha256_hex(const std::string &s)
{
    unsigned char d[SHA256_DIGEST_LENGTH];
    SHA256((const unsigned char*)s.data(), s.size(), d);
    char h[2 * SHA256_DIGEST_LENGTH + 1];
    for(int i = 0; i < SHA256_DIGEST_LENGTH; ++i) snprintf(h + 2 * i, 3, "%02x", d[i]);
    return std::string(h, 2 * SHA256_DIGEST_LENGTH);
}

static bool same(const std::string &a, const std::string &b)
{
    return a.size() == b.size() && CRYPTO_memcmp(a.data(), b.data(), a.size()) == 0;
}

// edge .device_auth (JSON) 의 "custom_password_hash" 값. null/없음/못 읽음이면 빈 값 (edge _auth_data 와 같음)
static std::string edge_custom_hash(void)
{
    std::string t = read_file(EDGE_AUTH_FILE);
    size_t k = t.find("\"custom_password_hash\"");
    if(k == std::string::npos) return std::string();
    size_t c = t.find(':', k);
    if(c == std::string::npos) return std::string();
    size_t q1 = t.find_first_not_of(" \t\r\n", c + 1);
    if(q1 == std::string::npos || t[q1] != '"') return std::string();   // null
    size_t q2 = t.find('"', q1 + 1);
    if(q2 == std::string::npos) return std::string();
    return t.substr(q1 + 1, q2 - q1 - 1);
}



// --- 받은 원문에서 wsse:Security/UsernameToken 읽기 (접두사는 아무거나) ---
static std::string xml_unescape(const std::string &s)
{
    std::string o;
    for(size_t i = 0; i < s.size(); ++i)
    {
        if(s[i] != '&') { o += s[i]; continue; }
        size_t e = s.find(';', i);
        if(e == std::string::npos || e - i > 10) { o += s[i]; continue; }
        std::string n = s.substr(i + 1, e - i - 1);
        unsigned long cp = 0; bool num = false;
        if(n == "amp") o += '&'; else if(n == "lt") o += '<'; else if(n == "gt") o += '>';
        else if(n == "quot") o += '"'; else if(n == "apos") o += '\'';
        else if(n.size() > 1 && n[0] == '#') { cp = (n[1] == 'x' || n[1] == 'X') ? strtoul(n.c_str() + 2, NULL, 16) : strtoul(n.c_str() + 1, NULL, 10); num = true; }
        else { o += s[i]; continue; }
        if(num)   // UTF-8 로
        {
            if(cp < 0x80) o += (char)cp;
            else if(cp < 0x800) { o += (char)(0xC0 | (cp >> 6)); o += (char)(0x80 | (cp & 0x3F)); }
            else if(cp < 0x10000) { o += (char)(0xE0 | (cp >> 12)); o += (char)(0x80 | ((cp >> 6) & 0x3F)); o += (char)(0x80 | (cp & 0x3F)); }
            else { o += (char)(0xF0 | (cp >> 18)); o += (char)(0x80 | ((cp >> 12) & 0x3F)); o += (char)(0x80 | ((cp >> 6) & 0x3F)); o += (char)(0x80 | (cp & 0x3F)); }
        }
        i = e;
    }
    return o;
}

// [from, to) 안에서 지역 이름이 local 인 첫 시작 태그. 찾으면 태그 끝('>' 다음) 위치, 속성 문자열, 빈 요소 여부
static size_t find_start(const std::string &x, size_t from, size_t to, const char *local,
                         std::string *attrs, bool *empty, size_t *tag_pos = NULL)
{
    size_t ll = strlen(local);
    for(size_t p = x.find('<', from); p != std::string::npos && p < to; p = x.find('<', p + 1))
    {
        size_t q = p + 1;
        if(q >= to || x[q] == '/' || x[q] == '?' || x[q] == '!') continue;
        size_t ne = q;
        while(ne < to && !strchr(" \t\r\n/>", x[ne])) ++ne;
        std::string name = x.substr(q, ne - q);
        size_t colon = name.rfind(':');
        std::string ln = colon == std::string::npos ? name : name.substr(colon + 1);
        if(ln.size() != ll || ln.compare(0, ll, local) != 0) continue;
        size_t gt = x.find('>', ne);
        if(gt == std::string::npos || gt >= to) return std::string::npos;
        if(attrs) *attrs = x.substr(ne, gt - ne);
        if(empty) *empty = gt > ne && x[gt - 1] == '/';
        if(tag_pos) *tag_pos = p;
        return gt + 1;
    }
    return std::string::npos;
}

// 요소 local 의 텍스트 (첫 번째). 없으면 false
static bool elem_text(const std::string &x, size_t from, size_t to, const char *local, std::string *text, std::string *attrs)
{
    bool empty = false;
    size_t s = find_start(x, from, to, local, attrs, &empty);
    if(s == std::string::npos) return false;
    if(empty) { text->clear(); return true; }
    size_t e = x.find("</", s);
    if(e == std::string::npos || e > to) return false;
    *text = xml_unescape(x.substr(s, e - s));
    return true;
}

struct UsernameToken { bool found = false; std::string user, pass, type, nonce, created; };

static UsernameToken parse_token(const std::string &x)
{
    UsernameToken t;
    size_t hdr = find_start(x, 0, x.size(), "Header", NULL, NULL);
    size_t body_tag = std::string::npos;
    find_start(x, 0, x.size(), "Body", NULL, NULL, &body_tag);
    if(hdr == std::string::npos) return t;
    size_t hend = body_tag == std::string::npos ? x.size() : body_tag;   // 헤더 안에서만 찾는다
    if(hend < hdr) return t;
    size_t sec_tag = 0;
    size_t sec = find_start(x, hdr, hend, "Security", NULL, NULL, &sec_tag);
    if(sec == std::string::npos) return t;
    size_t ut = find_start(x, sec, hend, "UsernameToken", NULL, NULL);
    if(ut == std::string::npos) return t;
    std::string a;
    if(!elem_text(x, ut, hend, "Username", &t.user, NULL)) return t;
    if(!elem_text(x, ut, hend, "Password", &t.pass, &a)) return t;
    size_t ty = a.find("Type");
    if(ty != std::string::npos) { size_t q1 = a.find_first_of("\"'", ty); size_t q2 = q1 == std::string::npos ? q1 : a.find(a[q1], q1 + 1);
                                  if(q2 != std::string::npos) t.type = a.substr(q1 + 1, q2 - q1 - 1); }
    elem_text(x, ut, hend, "Nonce", &t.nonce, NULL);
    elem_text(x, ut, hend, "Created", &t.created, NULL);
    t.user = trim_nl(t.user); t.nonce = trim_nl(t.nonce); t.created = trim_nl(t.created);
    t.found = true;
    return t;
}



// --- 잠금 (IP 별) ---
struct FailRec { int count; time_t until; };
static std::map<unsigned long, FailRec> g_fails;

static bool ip_locked(unsigned long ip)
{
    auto it = g_fails.find(ip);
    return it != g_fails.end() && it->second.until > time(NULL);
}

static bool ip_fail(unsigned long ip)      // 이번 실패로 잠겼으면 true
{
    if(g_fails.size() > 1024)
        for(auto it = g_fails.begin(); it != g_fails.end(); )
            it = (it->second.until <= time(NULL) && it->second.count < AUTH_MAX_FAILS) ? g_fails.erase(it) : std::next(it);
    FailRec &r = g_fails[ip];
    if(++r.count >= AUTH_MAX_FAILS) { r.until = time(NULL) + AUTH_LOCK_SEC; return true; }
    return false;
}



static const char *PRE_AUTH_OPS[] = {    // ONVIF Core: 로그인 전 허용 (PRE_AUTH)
    "GetSystemDateAndTime", "GetWsdlUrl", "GetServices", "GetServiceCapabilities",
    "GetCapabilities", "GetHostname", "GetEndpointReference", NULL
};

static std::string ip_str(unsigned long ip)
{
    char b[32];
    snprintf(b, sizeof(b), "%lu.%lu.%lu.%lu", (ip >> 24) & 255, (ip >> 16) & 255, (ip >> 8) & 255, ip & 255);
    return b;
}

static void auth_log(unsigned long ip, const char *op, const char *why, bool ok)
{
    // 같은 IP·결과·이유는 30초에 한 번만 (ODM 은 2초마다 다시 묻는다)
    static std::map<std::string, time_t> last;
    std::string k = ip_str(ip) + "|" + why;
    time_t now = time(NULL);
    auto it = last.find(k);
    if(it != last.end() && now - it->second < 30) return;
    if(last.size() > 1024) last.clear();
    last[k] = now;
    fprintf(stderr, "ONVIF-AUTH: %s %s from %s (%s)\n", ok ? "allowed" : "DENIED", op, ip_str(ip).c_str(), why);
    fflush(stderr);
}



// 확인 결과: true = 진행, false = 거부(why)
static bool mk3_authorize(struct soap *soap, const char *op, const char **why)
{
    *why = "";
    if(access(ONVIF_AUTH_OFF_FILE, F_OK) == 0) { *why = "auth off"; return true; }
    if(((soap->ip >> 24) & 255) == 127)        { *why = "local"; return true; }
    for(int i = 0; PRE_AUTH_OPS[i]; ++i)
        if(strcmp(op, PRE_AUTH_OPS[i]) == 0)   { *why = "pre-auth"; return true; }

    if(ip_locked(soap->ip)) { *why = "locked"; return false; }

    UsernameToken t = parse_token(g_rx);
    if(!t.found) { *why = "no-credentials"; return false; }   // 실패로 세지 않음

    std::string dev = trim_nl(read_file(DEVICE_ID_FILE));
    size_t dash = dev.rfind('-');
    std::string serial = dash == std::string::npos ? std::string() : dev.substr(dash + 1);
    if(dev.empty() || serial.empty()) { *why = "no-device-id"; return false; }   // 기준이 없으면 막는다

    std::string custom = edge_custom_hash();
    std::string plain;                         // 확인에 쓸 비밀번호 원문 (모르면 빈 값)
    bool text_by_hash = false;
    if(custom.empty())
        plain = serial;
    else
    {
        std::string f = read_file(ONVIF_AUTH_FILE);
        if(!f.empty() && f.back() == '\n') f.pop_back();   // 끝 줄바꿈 하나만 (비밀번호 앞뒤 공백은 그대로)
        if(!f.empty() && same(sha256_hex(dev + ":" + f), custom))
            plain = f;
        else
            text_by_hash = true;               // 원문 없음/옛 값 -> Text 만 해시로
    }

    bool digest = t.type.find("PasswordDigest") != std::string::npos;
    bool ok = false;
    if(t.user != ONVIF_USER)
        *why = "wrong-user";
    else if(digest)
    {
        if(plain.empty())
        {
            // 비밀번호가 틀린 게 아니라 확인할 원문이 없는 것 -> 실패로 세지 않는다 (ODM 이 스스로 잠기지 않게)
            *why = "digest-needs-password-file (set the web password again)";
            return false;
        }
        else
        {
            int nlen = 0;
            const char *nb = t.nonce.empty() ? "" : soap_base642s(soap, t.nonce.c_str(), NULL, 0, &nlen);
            if(!nb) { nb = ""; nlen = 0; }
            std::string in(nb, nlen);
            in += t.created; in += plain;
            unsigned char d[SHA_DIGEST_LENGTH];
            SHA1((const unsigned char*)in.data(), in.size(), d);
            char b64[64];
            soap_s2base64(soap, d, b64, SHA_DIGEST_LENGTH);
            ok = same(trim_nl(t.pass), std::string(b64));
            if(!ok) *why = "wrong-password";
        }
    }
    else
    {
        ok = text_by_hash ? same(sha256_hex(dev + ":" + t.pass), custom) : same(t.pass, plain);
        if(!ok) *why = "wrong-password";
    }

    if(ok) { g_fails.erase(soap->ip); *why = digest ? "digest" : "text"; return true; }
    if(ip_fail(soap->ip)) *why = "locked-now";
    return false;
}



static struct Namespace *g_ns_ter = NULL;      // 응답 namespace 표 + ter (NotAuthorized fault 용)

static void build_ns_ter(void)
{
    int n = 0;
    while(namespaces[n].id) ++n;
    g_ns_ter = (struct Namespace*)calloc(n + 2, sizeof(struct Namespace));
    if(!g_ns_ter) return;
    memcpy(g_ns_ter, namespaces, n * sizeof(struct Namespace));
    g_ns_ter[n].id = "ter";
    g_ns_ter[n].ns = "http://www.onvif.org/ver10/error";
}

// 이번 요청 확인. 거부했으면 fault 를 보내고 false
static bool mk3_check_request(struct soap *soap)
{
    const char *op = "";
    std::string opname;
    if(!soap_peek_element(soap))
    {
        const char *c = strchr(soap->tag, ':');
        opname = c ? c + 1 : soap->tag;
        op = opname.c_str();
    }
    const char *why = "";
    bool ok = mk3_authorize(soap, op, &why);
    if(ok)
    {
        if(strcmp(why, "digest") == 0 || strcmp(why, "text") == 0) auth_log(soap->ip, op, why, true);
        return true;
    }
    auth_log(soap->ip, op, why, false);
    if(g_ns_ter) soap_set_namespaces(soap, g_ns_ter);
    soap_sender_fault_subcode(soap, "ter:NotAuthorized", "Sender not Authorized", NULL);
    soap_send_fault(soap);
    return false;
}



void init_gsoap(void)
{
    soap = soap_new();

    if(!soap)
        daemon_error_exit("Can't get mem for SOAP\n");

    soap->fignore = mk3_fignore;   // MK3: WS-Security 헤더 허용
    g_orig_frecv  = soap->frecv;   // MK3: 계정 확인용으로 받은 원문 앞부분 보관
    soap->frecv   = mk3_frecv;
    build_ns_ter();

    soap->bind_flags = SO_REUSEADDR;

    if( !soap_valid_socket(soap_bind(soap, NULL, service_ctx.port, 10)) )
    {
        soap_stream_fault(soap, std::cerr);
        exit(EXIT_FAILURE);
    }

    soap->send_timeout = 3; // timeout in sec
    soap->recv_timeout = 3; // timeout in sec


    //save pointer of service_ctx in soap
    soap->user = (void*)&service_ctx;
}



void init(void *data)
{
    UNUSED(data);
    init_signals();
    check_service_ctx();
    init_gsoap();
    ptz_init();     // MK3: 모터 상태 확인 (기동돼 있으면 명령 없음, 아니면 S만)
}



int main(int argc, char *argv[])
{
    processing_cmd(argc, argv);
    daemonize2(init, nullptr);

    FOREACH_SERVICE(DECLARE_SERVICE, soap)

    while( true )
    {
        // wait new client
        if( !soap_valid_socket(soap_accept(soap)) )
        {
            soap_stream_fault(soap, std::cerr);
            return EXIT_FAILURE;
        }


        // process service
        g_rx.clear();
        if( soap_begin_serve(soap) )
        {
            soap_stream_fault(soap, std::cerr);
        }
        else if( !mk3_check_request(soap) )   // MK3: 계정 확인 (거부면 fault 를 보냄)
        {
        }
        FOREACH_SERVICE(DISPATCH_SERVICE, soap)
        else
        {
            DEBUG_MSG("Unknown service\n");
        }

        soap_destroy(soap); // delete managed C++ objects
        soap_end(soap);     // delete managed memory
    }


    return EXIT_FAILURE; // Error, normal exit from the main loop only through the signal handler.
}

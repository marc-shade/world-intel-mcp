#!/bin/bash
# Intel Collector Daemon Control
#
# Manages the world-intel-mcp collector daemon that periodically
# fetches global intelligence data across 30+ domains.
#
# Usage:
#   collector-daemon.sh start|stop|restart|status|logs

set -euo pipefail

PLIST_SRC="/Volumes/SSDRAID0/agentic-system/mcp-servers/world-intel-mcp/com.agentic.intel-collector.plist"
PLIST="$HOME/Library/LaunchAgents/com.agentic.intel-collector.plist"
LABEL="com.agentic.intel-collector"
LOG="/tmp/intel-collector.log"
ERR_LOG="/tmp/intel-collector-error.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

case "${1:-help}" in
    start)
        if launchctl list "$LABEL" &>/dev/null; then
            echo -e "${YELLOW}Intel collector already running${NC}"
            exit 0
        fi
        if [ ! -f "$PLIST" ]; then
            cp "$PLIST_SRC" "$PLIST"
        fi
        launchctl load "$PLIST"
        sleep 1
        if launchctl list "$LABEL" &>/dev/null; then
            echo -e "${GREEN}Intel collector started${NC} (interval: 300s)"
        else
            echo -e "${RED}Intel collector failed to start. Check:${NC} $ERR_LOG"
            exit 1
        fi
        ;;

    stop)
        if ! launchctl list "$LABEL" &>/dev/null; then
            echo -e "${YELLOW}Intel collector not running${NC}"
            exit 0
        fi
        launchctl unload "$PLIST"
        echo -e "${GREEN}Intel collector stopped${NC}"
        ;;

    restart)
        "$0" stop
        sleep 2
        "$0" start
        ;;

    status)
        echo "=== Intel Collector Status ==="
        echo ""
        if launchctl list "$LABEL" &>/dev/null; then
            PID=$(launchctl list "$LABEL" 2>/dev/null | head -1 | awk '{print $1}')
            echo -e "State: ${GREEN}RUNNING${NC} (PID: ${PID:-unknown})"
        else
            echo -e "State: ${RED}STOPPED${NC}"
        fi

        # Log file info
        if [ -f "$LOG" ]; then
            SIZE=$(du -h "$LOG" 2>/dev/null | awk '{print $1}')
            LAST=$(tail -1 "$LOG" 2>/dev/null | head -c 80)
            echo "Log size: $SIZE"
            echo "Last line: $LAST"
        else
            echo "Log: no output yet"
        fi

        # Error log
        if [ -f "$ERR_LOG" ] && [ -s "$ERR_LOG" ]; then
            ERR_SIZE=$(du -h "$ERR_LOG" 2>/dev/null | awk '{print $1}')
            echo -e "Errors: ${YELLOW}${ERR_SIZE}${NC} ($ERR_LOG)"
        else
            echo -e "Errors: ${GREEN}none${NC}"
        fi
        ;;

    logs)
        MODE="${2:-stdout}"
        case "$MODE" in
            err|error|stderr)
                if [ -f "$ERR_LOG" ]; then
                    tail -f "$ERR_LOG"
                else
                    echo -e "${YELLOW}No error log yet: $ERR_LOG${NC}"
                fi
                ;;
            *)
                if [ -f "$LOG" ]; then
                    tail -f "$LOG"
                else
                    echo -e "${YELLOW}No log file yet: $LOG${NC}"
                fi
                ;;
        esac
        ;;

    help|*)
        echo "Intel Collector Daemon Control"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "  start          Start the intel collector daemon"
        echo "  stop           Stop the intel collector daemon"
        echo "  restart        Restart the intel collector daemon"
        echo "  status         Show daemon state and log info"
        echo "  logs           Tail stdout log (follow mode)"
        echo "  logs err       Tail stderr log (follow mode)"
        ;;
esac

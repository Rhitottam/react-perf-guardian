#!/bin/bash
#
# React Performance PR Reviewer - CLI Tool
#
# Usage:
#   ./review-pr.sh <pr_number_or_url> [options]
#
# Arguments:
#   pr_number_or_url      Either a PR number (123) or full PR URL
#
# Options:
#   --severity <level>    Minimum severity (low|medium|high|critical) [default: medium]
#   --auto-approve        Auto-approve PRs with no critical issues
#   --analyze-only        Only analyze, don't post review
#   --help                Show this help message
#
# Environment Variables:
#   GITHUB_TOKEN          GitHub personal access token (required)
#   GITHUB_REPOSITORY     Repository in format 'owner/repo' (optional if using URL)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Help message
show_help() {
    cat << EOF
${BLUE}React Performance PR Reviewer${NC}

${GREEN}Usage:${NC}
  ./review-pr.sh <pr_number_or_url> [options]

${GREEN}Arguments:${NC}
  pr_number_or_url      Either:
                        - PR number (e.g., 123)
                        - Full PR URL (e.g., https://github.com/owner/repo/pull/123)

${GREEN}Options:${NC}
  --severity <level>    Minimum severity to report (low|medium|high|critical)
                        Default: medium
  --auto-approve        Approve PRs with no critical issues
  --analyze-only        Only analyze, don't post review comments
  --help                Show this help message

${GREEN}Environment Variables:${NC}
  GITHUB_TOKEN          GitHub personal access token (required)
                        Get one at: https://github.com/settings/tokens
                        
  GITHUB_REPOSITORY     Repository in format 'owner/repo'
                        (Optional if using PR URL - auto-detected from URL)
                        Example: facebook/react

${GREEN}Examples:${NC}
  # Using PR number (requires GITHUB_REPOSITORY)
  export GITHUB_REPOSITORY="owner/repo"
  ./review-pr.sh 123

  # Using PR URL (repository auto-detected)
  ./review-pr.sh https://github.com/owner/repo/pull/123

  # With options
  ./review-pr.sh https://github.com/owner/repo/pull/123 --severity high --auto-approve

  # Dry run
  ./review-pr.sh https://github.com/owner/repo/pull/123 --analyze-only

${GREEN}Setup:${NC}
  1. Create a GitHub Personal Access Token:
     https://github.com/settings/tokens/new
     Required scopes: repo (full control)
  
  2. Set environment variables:
     export GITHUB_TOKEN="ghp_xxxxxxxxxxxxx"
     export GITHUB_REPOSITORY="owner/repo"
  
  3. Or create a .env file in the agents/ directory:
     GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
     GITHUB_REPOSITORY=owner/repo
  
  4. Install dependencies:
     cd agents && pip install -r requirements.txt

${GREEN}Notes:${NC}
  - Only React/TypeScript files (.tsx, .ts, .jsx, .js) are analyzed
  - Issues are posted as inline PR review comments
  - Critical issues will trigger "Request Changes" status
  - Medium/low issues will be informational comments

EOF
}

# Check if help requested
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    show_help
    exit 0
fi

# Check PR number/URL provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: PR number or URL required${NC}"
    echo ""
    show_help
    exit 1
fi

PR_INPUT=$1
shift

# Get the agents directory
AGENTS_DIR="$(cd "$(dirname "$0")/agents" && pwd)"

# Load .env file if it exists
if [ -f "$AGENTS_DIR/.env" ]; then
    echo -e "${BLUE}🔍 Loading .env file...${NC}"
    # Load .env safely, handling values with spaces
    set -a  # automatically export all variables
    source "$AGENTS_DIR/.env"
    set +a  # disable auto-export
    echo -e "${GREEN}✅ .env file loaded${NC}"
fi

# Check environment
echo -e "${BLUE}🔍 Checking environment...${NC}"

if [ -z "$GITHUB_TOKEN" ]; then
    echo -e "${RED}❌ GITHUB_TOKEN not set${NC}"
    echo "   Set it with: export GITHUB_TOKEN='your-token'"
    echo "   Or add to agents/.env file: GITHUB_TOKEN=your-token"
    exit 1
fi

# Check if input is a URL or PR number
IS_URL=false
if [[ "$PR_INPUT" == *"github.com"* ]] || [[ "$PR_INPUT" == http* ]]; then
    IS_URL=true
    echo -e "${GREEN}✅ Using PR URL (repository will be auto-detected)${NC}"
else
    # It's a PR number, so GITHUB_REPOSITORY is required
    if [ -z "$GITHUB_REPOSITORY" ]; then
        echo -e "${RED}❌ GITHUB_REPOSITORY not set${NC}"
        echo "   When using PR number, you must set GITHUB_REPOSITORY"
        echo "   Set it with: export GITHUB_REPOSITORY='owner/repo'"
        echo "   Or use the full PR URL instead: https://github.com/owner/repo/pull/$PR_INPUT"
        exit 1
    fi
    echo -e "${GREEN}✅ Using PR number${NC}"
    echo "   Repository: $GITHUB_REPOSITORY"
fi

echo "   Token: ${GITHUB_TOKEN:0:7}..."
echo ""

# Check Python environment
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ python3 not found${NC}"
    exit 1
fi

# Check if in virtual environment (recommended but not required)
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}⚠️  Not in a virtual environment${NC}"
    echo "   Recommended: cd agents && source venv/bin/activate"
    echo ""
fi

# Check dependencies
echo -e "${BLUE}📦 Checking dependencies...${NC}"

if [ ! -f "$AGENTS_DIR/github_integration.py" ]; then
    echo -e "${RED}❌ github_integration.py not found${NC}"
    echo "   Expected at: $AGENTS_DIR/github_integration.py"
    exit 1
fi

# Run the analyzer
if [ "$IS_URL" = true ]; then
    echo -e "${BLUE}🚀 Analyzing PR from URL...${NC}"
else
    echo -e "${BLUE}🚀 Analyzing PR #${PR_INPUT}...${NC}"
fi
echo "=" * 60
echo ""

cd "$AGENTS_DIR"

# Run Python script with all arguments
python3 github_integration.py "$PR_INPUT" "$@"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Analysis complete!${NC}"
else
    echo -e "${RED}❌ Analysis failed with exit code $EXIT_CODE${NC}"
fi

exit $EXIT_CODE


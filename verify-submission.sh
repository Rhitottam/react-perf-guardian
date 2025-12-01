#!/bin/bash
#
# Pre-submission verification script
# Checks that everything is ready for submission
#

echo "🔍 Verifying Project Submission Readiness"
echo "=========================================="
echo ""

CHECKS_PASSED=0
CHECKS_FAILED=0

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✅${NC} $1"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "${RED}❌${NC} $1"
        ((CHECKS_FAILED++))
        return 1
    fi
}

check_dir() {
    if [ -d "$1" ]; then
        echo -e "${GREEN}✅${NC} $1/"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "${RED}❌${NC} $1/"
        ((CHECKS_FAILED++))
        return 1
    fi
}

# Check essential files
echo "📄 Essential Files:"
check_file "README.md"
check_file "SETUP.md"
check_file "LICENSE"
check_file "Dockerfile"
check_file "docker-compose.yml"
check_file ".dockerignore"
check_file ".env.example"
check_file "review-pr.sh"
echo ""

# Check directories
echo "📁 Essential Directories:"
check_dir "parser"
check_dir "agents"
check_dir "examples"
check_dir ".github/workflows"
echo ""

# Check parser files
echo "🔧 Parser Files:"
check_file "parser/package.json"
check_file "parser/tsconfig.json"
check_file "parser/src/analyzer.ts"
check_file "parser/src/cli.ts"
check_file "parser/src/types.ts"
echo ""

# Check agent files
echo "🤖 Agent Files:"
check_file "agents/agents.py"
check_file "agents/main.py"
check_file "agents/tools.py"
check_file "agents/github_integration.py"
check_file "agents/parser_bridge.py"
check_file "agents/requirements.txt"
check_file "agents/verify-setup.py"
echo ""

# Check examples
echo "📝 Example Files:"
check_file "examples/UserList.tsx"
check_file "examples/UserCard.tsx"
echo ""

# Check GitHub workflow
echo "🚀 GitHub Action:"
check_file ".github/workflows/react-perf-review.yml"
echo ""

# Check for unwanted files
echo "🧹 Checking for Debug Files:"
DEBUG_FILES=0
if ls *.md 2>/dev/null | grep -E "(DEBUGGING|TROUBLESHOOTING|LOG_|AGENT_OUTPUT|WHATS_NEW|PR_URL_|GITHUB_PR_|ENV_SETUP)" >/dev/null; then
    echo -e "${YELLOW}⚠️${NC}  Found debug markdown files (should be removed)"
    ((DEBUG_FILES++))
fi

if [ -d "test-files" ]; then
    echo -e "${YELLOW}⚠️${NC}  Found test-files/ directory (should be examples/)"
    ((DEBUG_FILES++))
fi

if [ $DEBUG_FILES -eq 0 ]; then
    echo -e "${GREEN}✅${NC} No debug files found"
    ((CHECKS_PASSED++))
else
    echo -e "${RED}❌${NC} Found $DEBUG_FILES debug artifacts"
    ((CHECKS_FAILED++))
fi
echo ""

# Check parser build
echo "⚙️  Checking Parser:"
if [ -d "parser/dist" ]; then
    if [ -f "parser/dist/cli.js" ]; then
        echo -e "${GREEN}✅${NC} Parser is built"
        ((CHECKS_PASSED++))
    else
        echo -e "${YELLOW}⚠️${NC}  Parser needs to be built (run: cd parser && npm run build)"
        ((CHECKS_FAILED++))
    fi
else
    echo -e "${YELLOW}⚠️${NC}  Parser not built yet (run: cd parser && npm install && npm run build)"
    ((CHECKS_FAILED++))
fi
echo ""

# Check for .env file
echo "🔒 Environment Configuration:"
if [ -f ".env" ]; then
    echo -e "${YELLOW}⚠️${NC}  .env file exists (make sure it's in .gitignore)"
else
    echo -e "${GREEN}✅${NC} No .env file in root (good - users will create their own)"
    ((CHECKS_PASSED++))
fi

if [ -f "agents/.env" ]; then
    echo -e "${YELLOW}⚠️${NC}  agents/.env file exists (make sure it's in .gitignore)"
else
    echo -e "${GREEN}✅${NC} No .env file in agents/ (good - users will create their own)"
    ((CHECKS_PASSED++))
fi
echo ""

# Check .gitignore
echo "🔒 Git Configuration:"
if grep -q ".env" .gitignore 2>/dev/null; then
    echo -e "${GREEN}✅${NC} .env is in .gitignore"
    ((CHECKS_PASSED++))
else
    echo -e "${RED}❌${NC} .env should be in .gitignore"
    ((CHECKS_FAILED++))
fi
echo ""

# Summary
echo "=========================================="
echo "📊 Summary:"
echo ""
echo -e "${GREEN}Checks Passed: $CHECKS_PASSED${NC}"
echo -e "${RED}Checks Failed: $CHECKS_FAILED${NC}"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 Project is ready for submission!${NC}"
    echo ""
    echo "📋 Final Checklist:"
    echo "   1. ✅ All essential files present"
    echo "   2. ✅ No debug files"
    echo "   3. ✅ Examples folder exists"
    echo "   4. ✅ Documentation complete"
    echo "   5. ✅ Docker files configured"
    echo ""
    echo "🚀 Next Steps:"
    echo "   - Review README.md"
    echo "   - Test Docker build (if Docker is installed)"
    echo "   - Submit the project"
    exit 0
else
    echo -e "${RED}⚠️  Some checks failed. Review the issues above.${NC}"
    echo ""
    echo "💡 Common fixes:"
    echo "   - Build parser: cd parser && npm run build"
    echo "   - Remove debug files: rm -f DEBUGGING*.md TROUBLESHOOTING.md"
    echo "   - Move test files: mv test-files examples"
    exit 1
fi


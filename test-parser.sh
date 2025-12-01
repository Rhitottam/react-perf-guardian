#!/bin/bash

# Quick parser test script

echo "🧪 Testing React Performance Parser"
echo "===================================="
echo ""

cd "$(dirname "$0")/parser"

echo "📦 Building parser..."
npm run build
echo ""

echo "✅ Testing UserList.tsx..."
node dist/cli.js ../examples/UserList.tsx > /tmp/userlist-output.json
if [ $? -eq 0 ]; then
    echo "   ✓ Parsed successfully"
    COMPONENTS=$(cat /tmp/userlist-output.json | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['metadata']['totalComponents'])")
    echo "   ✓ Found $COMPONENTS component(s)"
    echo ""
else
    echo "   ✗ Failed to parse"
    exit 1
fi

echo "✅ Testing UserCard.tsx..."
node dist/cli.js ../examples/UserCard.tsx > /tmp/usercard-output.json
if [ $? -eq 0 ]; then
    echo "   ✓ Parsed successfully"
    IS_MEMOIZED=$(cat /tmp/usercard-output.json | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['components'][0]['isMemoized'])")
    echo "   ✓ Memoization detected: $IS_MEMOIZED"
    echo ""
else
    echo "   ✗ Failed to parse"
    exit 1
fi

echo "🎉 All parser tests passed!"
echo ""
echo "📊 Detailed output saved to:"
echo "   - /tmp/userlist-output.json"
echo "   - /tmp/usercard-output.json"
echo ""
echo "💡 To view pretty output:"
echo "   cat /tmp/userlist-output.json | python3 -m json.tool"


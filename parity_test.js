/* 一致性对账：从 HTML 里抽出 JS 引擎，与 Python 引擎逐例比对打分结果。
   运行： node parity_test.js
*/
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { execFileSync } = require('child_process');

const HTML = path.join(__dirname, 'e护校园_反诈研判_静态版.html');
const html = fs.readFileSync(HTML, 'utf8');

// 抽出引擎代码块（SCAM_RULES 开头 → analyzeLocal 函数结束）
const start = html.indexOf('var SCAM_RULES');
const endMarker = '/* ==========================================================================\n   界面逻辑';
const end = html.indexOf(endMarker);
if (start < 0 || end < 0) {
  console.error('❌ 未能从 HTML 中定位引擎代码块');
  process.exit(2);
}
const engineCode = html.slice(start, end);

const sandbox = { console };
vm.createContext(sandbox);
vm.runInContext(engineCode + '\nthis.analyzeLocal = analyzeLocal;', sandbox);
const analyzeLocalJS = sandbox.analyzeLocal;

const CASES = {
  '快递理赔+屏幕共享': '您好，我是快递公司客服，您的包裹在运输中丢失了，我们双倍理赔。请下载XX会议APP并开启屏幕共享，把收到的验证码发给我，我们马上把退款打到您账户。',
  '刷单返利': '亲，帮忙刷个单，一单返15元。先垫付98元，完成后本金佣金一起返。任务简单，几分钟搞定，日结不拖欠。',
  '冒充老师借钱': '小李，我是王老师，这是我新号。我现在在外面有点急事，你先转2000给我，回去就还你。别跟其他同学说。',
  '冒充公检法': '这里是XX市公安局，你的身份信息被人用于洗钱，现需配合资金清查。请将名下资金转入我们的安全账户，不得告知任何人，否则将依法拘留。',
  '校园贷注销': '同学你好，你在校期间注册的校园贷账户需要注销，否则将影响个人征信。请配合清空贷款额度，我们协助你完成注销，全程免费。',
  '游戏交易解冻费': '低价出游戏账号，走担保交易，账号被冻结需要交解冻费。',
  '门票代抢': '演唱会内场门票代抢，实名转让，先付溢价定金。',
  '兼职押金': '招聘校园兼职，先交200元服装费和体检费，入职后工资日结。',
  '正规助学金通知': '本学期国家助学金材料请于本周五前交到学院办公室A302，由辅导员统一审核，学校不会通过电话或链接收集银行卡信息。',
  '正常快递短信': '您的快递已放在菜鸟驿站3号柜，取件码8823，请凭码自行领取。',
  '日常闲聊': '今天下午三点图书馆三楼开会，记得带笔记本。',
  '恐吓型': '你涉嫌犯罪，必须配合调查，否则后果自负。',
};

// 让 Python 引擎跑同一批用例
const pyScript = `
import io, json, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from anti_fraud_engine import analyze_local
cases = json.loads(sys.argv[1])
out = {}
for name, text in cases.items():
    r = analyze_local(text)
    out[name] = {"level": r["risk_level"], "score": r["risk_score"], "type": r["scam_type"]}
print(json.dumps(out, ensure_ascii=False))
`;

const pyOut = execFileSync('python', ['-c', pyScript, JSON.stringify(CASES)], {
  cwd: __dirname, encoding: 'utf8',
});
const pyResults = JSON.parse(pyOut.trim());

let pass = 0, fail = 0;
const pad = (s, n) => String(s).padEnd(n, ' ');

console.log(pad('用例', 20) + pad('JS 等级/分值', 18) + pad('Python 等级/分值', 20) + '结果');
console.log('-'.repeat(74));

for (const [name, text] of Object.entries(CASES)) {
  const js = analyzeLocalJS(text);
  const py = pyResults[name];
  const same = js.risk_level === py.level && js.risk_score === py.score && js.scam_type === py.type;
  if (same) pass++; else fail++;
  console.log(
    pad(name, 20) +
    pad(`${js.risk_level} ${js.risk_score}`, 18) +
    pad(`${py.level} ${py.score}`, 20) +
    (same ? '✅ 一致' : `❌ 不一致（类型 ${js.scam_type} vs ${py.type}）`)
  );
}

console.log('-'.repeat(74));
console.log(`一致 ${pass} 例，不一致 ${fail} 例`);
process.exit(fail === 0 ? 0 : 1);

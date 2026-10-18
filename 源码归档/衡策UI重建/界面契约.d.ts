/** UI 自定义接入协议。不是 DeepSeek Harness 官方 SDK 声明。 */
export type MoneyFen = number;
export type BasisPoints = number;
export type ModuleName = '收入' | '成本' | '费用' | '采购';
export type Category = '预算基础' | '实时经营' | '行业对标' | '经营变更';
export type TaskStatus = 'pending' | 'doing' | 'done';
export interface AnalysisConfig {
  cycle: '月度' | '季度';
  /** 月度 YYYY-MM；季度 YYYY-Qn。 */
  period: string;
  growth: BasisPoints;
  industry: BasisPoints | null;
  industryCorrection: boolean;
  industryThreshold: BasisPoints;
  noise: BasisPoints;
  significance: BasisPoints;
  tiers: Array<{ name: string; color: string; threshold: BasisPoints }>;
}
export interface VarianceRow {
  id: string;
  subject: string;
  module: ModuleName;
  department: string;
  departmentId: string;
  period: string;
  budget: MoneyFen;
  actual: MoneyFen;
  variance: MoneyFen;
  rate: BasisPoints;
  /** 使用后端判定，不根据有利/不利自行重判。 */
  risk: 'high' | 'watch' | 'normal';
  tierName?: string;
  tierColor?: string;
  direction: 'favorable' | 'unfavorable';
  decision: string;
  reason: string;
  source: string;
}
export interface Workspace {
  schemaVersion: '1.0';
  demo: boolean;
  dirty?: boolean;
  meta: { company: string; period: string; scenario: string; generatedAt: string; runId: string };
  config: AnalysisConfig;
  entities: Array<{ id: string; name: string }>;
  files: Array<{
    id: string; name: string; category: Category | '待识别';
    status: 'valid' | 'pending'; checks: number; rows: number;
    size: number | string; entity: string;
  }>;
  rows: VarianceRow[];
  /** 使用实际期间数；支持月/季、空序列及 null 实际值。 */
  trend: Array<{ period: string; budget: MoneyFen | null; actual: MoneyFen | null; rolling: MoneyFen | null }>;
  actions: Array<{
    id: string; rowId: string; title: string; department: string; owner: string;
    due: string; status: TaskStatus; priority: 'high' | 'watch';
    type: 'revision' | 'execution'; description: string;
  }>;
  revisions: Array<{
    id: string; rowId: string; subject: string; period: string; amount: MoneyFen;
    reason: string; approved: boolean; createdAt: string; demo?: boolean;
  }>;
  reports: Array<{
    id: string; title: string; period: string; createdAt: string;
    status: 'ready'; format: string; pages: number | null; includeAI?: boolean; demo?: boolean;
  }>;
  history: Array<{ id: string; period: string; createdAt: string; company: string; status: 'done'; riskCount: number }>;
  kpis: Array<{ name: string; value: BasisPoints | null; unit: '%'; note: string }>;
  background: { changeStatus: 'yes' | 'none' | 'unknown'; text: string };
  warnings?: Array<string | { message: string }>;
}
export type DownloadResult = { name: string; mime: string; bytes: ArrayBuffer | Uint8Array } | { handled: true };
export interface ActionMap {
  'workspace.load': { input: Record<string, never>; output: Workspace };
  'files.import': { input: { files: Array<{ name: string; size: number; bytes: ArrayBuffer }>; mode: 'append' | 'replace'; category: Category | null }; output: Workspace };
  'files.remove': { input: { id: string }; output: Workspace };
  'templates.download': { input: { category: Category }; output: DownloadResult };
  'analysis.run': { input: { entityId: string; config: AnalysisConfig }; output: Workspace };
  'background.save': { input: Workspace['background']; output: Workspace };
  'actions.update': { input: { id: string; status: TaskStatus }; output: Workspace };
  'revisions.approve': { input: { rowId: string; period: string; amount: MoneyFen; reason: string; approved: true }; output: Workspace };
  'reports.generate': { input: { runId: string; includeAI: boolean }; output: Workspace };
  'reports.export': { input: { id: string; format: 'pdf' | 'html' | 'md' | 'json' }; output: DownloadResult };
  'reports.openFolder': { input: { id: string }; output: { handled: true } };
  'history.open': { input: { id: string }; output: Workspace };
  'assistant.ask': {
    input: { question: string; context: { entityId: string; period: string; rowId?: string; runId: string }; dataAccess: boolean };
    output: { text: string; sources?: Array<{ title: string; excerpt: string }> } | { handled: true };
  };
}
export type HostEvent =
  | { type: 'workspace.changed'; data: Workspace }
  | { type: 'analysis.progress'; data: { message: string; percent?: number } }
  | { type: 'assistant.message'; data: { text: string } };
export interface HengceHost {
  version: '1.0';
  request<K extends keyof ActionMap>(action: K, payload: ActionMap[K]['input']): Promise<ActionMap[K]['output']>;
  subscribe?(callback: (event: HostEvent) => void): () => void;
}
declare global { interface Window { hengceHost?: HengceHost; } }

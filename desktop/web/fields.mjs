// One schema for visible labels, input units and serialisation. Blank fields remain null.
export const kpiFields=[
 ['shouru_shiji_fen','实际营收','元'],['shouru_yusuan_fen','预算营收','元'],
 ['kekong_chengben_shiji_fen','实际可控成本','元'],['kekong_chengben_yusuan_fen','预算可控成本','元'],
 ['feiyong_shiji_fen','实际费用','元'],['feiyong_yusuan_fen','预算费用','元'],['maoli_fen','毛利','元'],
 ['jingshui_fen','税后净利润','元'],['pbit_fen','息税前利润','元'],['ziben_zhanyong_fen','资本占用','元'],
 ['liudong_zichan_qichu_fen','期初流动资产','元'],['liudong_zichan_qimo_fen','期末流动资产','元'],
 ['liudong_fuzhai_qichu_fen','期初流动负债','元'],['liudong_fuzhai_qimo_fen','期末流动负债','元'],
 ['caigou_benqi_fen','本期采购成本','元'],['caigou_shangqi_fen','上期采购成本','元'],
 ['shiji_chanchu','实际产出','个'],['qianzai_channeng','潜在产能','个'],['dingdan_zongshu','订单总数','单'],
 ['lvyue_dingdan_shu','履约订单数','单'],['jiaofu_zhouqi_tian_shu','交付周期','天'],['manyi_keshu','满意客户数','人'],
 ['shoufang_keshu','受访客户数','人'],['jihua_yewu_liang','计划业务量','个'],['wancheng_yewu_liang','完成业务量','个'],['yichang_shijian_shu','异常事项数','次']];
export const splitFields=[['biaozhun_danjia_fen','原标准单价','元'],['biaozhun_yongliang','原单位用量','个'],['xiuding_danjia_fen','修订单价','元'],['xiuding_yongliang','修订单位用量','个'],['shiji_chanliang','实际产量','个'],['shiji_yongliang','实际总用量','个'],['shiji_chengben_fen','实际总成本','元']];
export const kpiNames=['营收达成率','成本控制率','费用偏差率','毛利率','净利润率','销售利润率','资产周转率','资金周转率','采购成本变动率','供应链履约率','产能利用率','交付周期','客户满意度','业务完成进度','异常事项数量'];
export function scaled(raw,label,scale=100,required=false){
 if(raw===null||raw===undefined||String(raw).trim()===''){if(required)throw new Error(`请填写${label}`);return null;}
 const s=String(raw).trim();if(!/^-?\d+(?:\.\d{1,2})?$/.test(s))throw new Error(`${label}最多保留两位小数`);
 const negative=s.startsWith('-'),[whole,fraction='']=s.replace('-','').split('.');
 if(scale===1 && fraction && /[1-9]/.test(fraction))throw new Error(`${label}须为整数`);
 const value=scale===100?Number(BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0'))):Number(whole);
 if(!Number.isSafeInteger(value))throw new Error(`${label}超出数值范围`);
 return negative?-value:value;
}

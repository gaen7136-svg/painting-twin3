import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.optimize import linear_sum_assignment
import time
import random

st.set_page_config(page_title="YULfactory: 보건 안전 통합 관제", layout="wide")

# --- [1. 데이터 초기화] ---
if 'workers' not in st.session_state:
    ids = [f'W_{i+1:02d}' for i in range(30)]
    levels = ['전문가']*5 + ['숙련공']*15 + ['신입']*10
    TWA_toluene = random.randint(0, 200)
    TWA_Xylene = random.randint(0,400)
    TWA_Ketone = random.randint(0,800)
    np.random.shuffle(levels)
    st.session_state.workers = pd.DataFrame({
        'ID': ids, 'Level': levels,
        'Skill_Weight': [1.2 if l == '전문가' else 1.0 if l == '숙련공' else 0.7 for l in levels],
        'Condition': 1.0, 'Cum_Exp': 0.0, 'Work_Time': 0.0,
        'is_present': True, 'Status': '대기',
        'TWA_toluene': TWA_toluene, 'TWA_Xylene': TWA_Xylene, 'TWA_Ketone': TWA_Ketone
    })
    st.session_state.colors = {f'W_{i+1:02d}': f'hsl({i*12}, 70%, 50%)' for i in range(30)}
    st.session_state.log = ["🚀 안전 관제 시스템 가동"]

# --- [2. 사이드바: 실시간 제어] ---
with st.sidebar:
    st.header("🕹️ 실시간 제어판")
    on_duty_ids = st.session_state.workers[st.session_state.workers['Status'] == '근무']['ID'].tolist()
    target = st.selectbox("컨디션 하락 타겟", on_duty_ids if on_duty_ids else ["없음"])
    if st.button("⚠️ 즉시 컨디션 저하"):
        if target != "없음":
            st.session_state.workers.loc[st.session_state.workers['ID'] == target, 'Condition'] = 0.2
            st.toast(f"{target} 긴급 교체 리스트 등록")

    st.divider()
    st.subheader("🏬 30인 출근 현황")
    for i in range(30):
        w = st.session_state.workers.iloc[i]
        cb = st.checkbox(f"{w['ID']} ({w['Level']})", value=w['is_present'], key=f"p_{w['ID']}")
        if cb != st.session_state.workers.at[i, 'is_present']:
            st.session_state.workers.at[i, 'is_present'] = cb
            if not cb: st.session_state.workers.at[i, 'Status'] = '퇴근'
            st.rerun()

# --- [3. 메인 관제 로직 (Fragment 1.5초 주기)] ---
@st.fragment(run_every=1.5)
def update_dashboard():
    workers = st.session_state.workers
    
    # A. 인력 교체 로직 (핵심 수정 부분)
    # 퇴출 조건: 1. 시간 종료(8s) / 2. 컨디션 난조(<0.4) / 3. 누적 노출량 초과(>=100) / 4. 미출근
    # 산업안전보건법 기준을 모사한 임계치(Threshold) 설정
    LIMIT_EXPOSURE = 70.0 
    
    to_exit = workers[(workers['Status'] == '근무') & 
                      ((workers['Work_Time'] >= 8.0) | 
                       (workers['Condition'] < 0.4) | 
                       (workers['Cum_Exp'] >= LIMIT_EXPOSURE) |
                       (~workers['is_present']))]
    
    for idx in to_exit.index:
        w = workers.loc[idx]
        st.session_state.workers.at[idx, 'Status'] = '퇴근'
        
        # 사유 판별 로그
        if w['Cum_Exp'] >= LIMIT_EXPOSURE:
            reason = "노출량 초과"
        elif w['Condition'] < 0.4:
            reason = "긴급보건"
        else:
            reason = "교대시간"
        st.session_state.log.append(f"🚨 {w['ID']} 교체 ({reason})")

    # 무한 루프 리셋 (대기자 부족 시)
    if len(workers[(workers['Status'] == '대기') & (workers['is_present'])]) < 5:
        # 리셋 시 노출량도 초기화하여 선순환 구조 형성
        st.session_state.workers.loc[(st.session_state.workers['Status'] == '퇴근') & (workers['is_present']), ['Work_Time', 'Status', 'Condition', 'Cum_Exp']] = [0.0, '대기', 1.0, 0.0]
        st.session_state.log.append("♻️ 전원 휴식 및 데이터 리셋")

    # 투입 (10명 유지)
    current_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무']
    if len(current_duty) < 10:
        needed = 10 - len(current_duty)
        # 노출량이 가장 적었던 사람부터 우선 순위 배정 (보건 안전 최적화)
        available = st.session_state.workers[(st.session_state.workers['Status'] == '대기') & (workers['is_present'])].sort_values('Cum_Exp')
        for idx in available.iloc[:needed].index:
            st.session_state.workers.at[idx, 'Status'] = '근무'

    # B. 배정 및 시각화
    on_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무'].head(10)
    
    if len(on_duty) == 10:
        voc_matrix = np.random.randint(10, 100, (2, 5))
        booths = [{'X': c+1, 'Y': 2-r, 'VOC': voc_matrix[r, c]} for r in range(2) for c in range(5)]
        
        # 헝가리안 최적 배정
        cost_matrix = np.zeros((10, 10))
        for i in range(10):
            w = on_duty.iloc[i]
            for j in range(10):
                b = booths[j]
                sens = 2.0 if w['Level'] == '신입' else 1.0
                cost_matrix[i, j] = (sens * b['VOC'] + w['Cum_Exp']) / (w['Skill_Weight'] * w['Condition'])
        
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        col_left, col_right = st.columns([2.5, 1])
        with col_left:
            st.subheader("🌐 실시간 공정 디지털 트윈")
            fig = go.Figure(go.Heatmap(z=voc_matrix, x=[1,2,3,4,5], y=[1,2], colorscale='RdYlGn_r', zmin=0, zmax=100, opacity=0.4))
            
            for i in range(len(row_ind)):
                w = on_duty.iloc[row_ind[i]]
                b = booths[col_ind[i]]
                # 0.5초당 노출량 업데이트 (농도에 비례)
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Work_Time'] += 0.5
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Cum_Exp'] += b['VOC'] * 0.1 # 가중치 증가
                
                # 시각적 알림 (노출량 80 이상이면 주황 테두리, 컨디션 불량이면 빨강)
                border = 'red' if w['Condition'] < 0.5 else ('orange' if w['Cum_Exp'] > 80 else 'white')
                fig.add_trace(go.Scatter(x=[b['X']], y=[b['Y']], mode="markers+text",
                    marker=dict(size=45, color=st.session_state.colors[w['ID']], line=dict(width=4, color=border)),
                    text=[f"<b>{w['ID']}</b>"], textposition="middle center", showlegend=False))
            fig.update_layout(height=450, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        with col_right:
            st.subheader("📊 안전 데이터 보드")
            # 노출량 임계치 시각화 포함
            st.progress(min(on_duty['Cum_Exp'].max() / 100, 1.0), text=f"현장 최대 노출 농도 ({round(on_duty['Cum_Exp'].max(),1)}/100)")

            # TWA 화학물질 임계치 감시
            TWA_THRESHOLDS = {
                'Toluene': 50,
                'Xylene': 100,
                'Ketone': 200
            }
            twa_toluene = workers['TWA_toluene'].iloc[0]
            twa_xylene = workers['TWA_Xylene'].iloc[0]
            twa_ketone = workers['TWA_Ketone'].iloc[0]
            twa_exceeded = (
                twa_toluene > TWA_THRESHOLDS['Toluene'] or
                twa_xylene > TWA_THRESHOLDS['Xylene'] or
                twa_ketone > TWA_THRESHOLDS['Ketone']
            )

            st.markdown("### 🧪 TWA 노출 현황")
            twa_cols = st.columns(3)
            twa_cols[0].metric("Toluene", f"{twa_toluene} ppm", f"기준 {TWA_THRESHOLDS['Toluene']} ppm")
            twa_cols[1].metric("Xylene", f"{twa_xylene} ppm", f"기준 {TWA_THRESHOLDS['Xylene']} ppm")
            twa_cols[2].metric("Ketone", f"{twa_ketone} ppm", f"기준 {TWA_THRESHOLDS['Ketone']} ppm")
            if twa_exceeded:
                st.error("🚨 TWA 임계치 초과: 한 개 이상의 화학물질이 기준치를 넘었습니다.")
            else:
                st.success("✅ 모든 TWA 수치가 기준치 이하입니다.")
            
            status_df = on_duty[['ID', 'Level', 'Condition', 'Work_Time', 'Cum_Exp']].copy()
            status_df.columns = ['ID', '숙련도', '컨디션', '시간(s)', '누적 노출량']
            
            st.dataframe(
                status_df.sort_values('누적 노출량', ascending=False).style.format({
                    '컨디션': '{:.2f}', '시간(s)': '{:.1f}', '누적 노출량': '{:.1f}'
                }).background_gradient(subset=['누적 노출량'], cmap='YlOrRd'),
                hide_index=True, use_container_width=True
            )
            st.divider()
            st.caption("최근 안전 로그")
            for l in st.session_state.log[-4:]: st.write(f"· {l}")
    else:
        st.error("🚨 인력 부족! 공정 가동이 일시 중단되었습니다.")

st.title("🛡️ YULfactory: 보건 안전 지능형 관제 시스템")
update_dashboard()

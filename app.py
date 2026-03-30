import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.optimize import linear_sum_assignment
import time

st.set_page_config(page_title="YULfactory: 통합 보건 관제", layout="wide")

# --- [1. 데이터 초기화] ---
if 'workers' not in st.session_state:
    ids = [f'W_{i+1:02d}' for i in range(30)]
    levels = ['전문가']*5 + ['숙련공']*15 + ['신입']*10
    np.random.shuffle(levels)
    st.session_state.workers = pd.DataFrame({
        'ID': ids, 'Level': levels,
        'Skill_Weight': [1.2 if l == '전문가' else 1.0 if l == '숙련공' else 0.7 for l in levels],
        'Condition': 1.0, 'Cum_Exp': 0.0, 'Work_Time': 0.0,
        'is_present': True, 'Status': '대기'
    })
    st.session_state.colors = {f'W_{i+1:02d}': f'hsl({i*12}, 70%, 50%)' for i in range(30)}
    st.session_state.log = ["🚀 관제 시스템 가동"]

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
    
    # A. 인력 교체 로직
    # 퇴출: 시간종료(8s), 컨디션난조(<0.4), 미출근
    to_exit = workers[(workers['Status'] == '근무') & 
                      ((workers['Work_Time'] >= 8.0) | (workers['Condition'] < 0.4) | (~workers['is_present']))]
    for idx in to_exit.index:
        st.session_state.workers.at[idx, 'Status'] = '퇴근'
        st.session_state.log.append(f"🚨 {workers.at[idx, 'ID']} 교체 완료")

    # 무한 루프 리셋 (대기자 부족 시)
    if len(workers[(workers['Status'] == '대기') & (workers['is_present'])]) < 5:
        st.session_state.workers.loc[(workers['Status'] == '퇴근') & (workers['is_present']), ['Work_Time', 'Status', 'Condition']] = [0.0, '대기', 1.0]
        st.session_state.log.append("♻️ 사이클 리셋 및 컨디션 회복")

    # 투입 (10명 유지)
    current_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무']
    if len(current_duty) < 10:
        needed = 10 - len(current_duty)
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
                # 데이터 업데이트 (0.5초치 가중치)
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Work_Time'] += 0.5
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Cum_Exp'] += b['VOC'] * 0.05 
                
                border = 'red' if w['Condition'] < 0.5 else 'white'
                fig.add_trace(go.Scatter(x=[b['X']], y=[b['Y']], mode="markers+text",
                    marker=dict(size=45, color=st.session_state.colors[w['ID']], line=dict(width=4, color=border)),
                    text=[f"<b>{w['ID']}</b>"], textposition="middle center", showlegend=False))
            fig.update_layout(height=450, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        with col_right:
            st.subheader("📊 근무자 실시간 상태")
            status_df = on_duty[['ID', 'Level', 'Condition', 'Work_Time', 'Cum_Exp']].copy()
            status_df.columns = ['ID', '숙련도', '컨디션', '시간(s)', '누적 노출량']
            
            # 소수점 포맷팅 및 하이라이트
            st.dataframe(
                status_df.sort_values('누적 노출량', ascending=False).style.format({
                    '컨디션': '{:.2f}',
                    '시간(s)': '{:.1f}',
                    '누적 노출량': '{:.1f}'
                }).background_gradient(subset=['누적 노출량'], cmap='OrRd'),
                hide_index=True, use_container_width=True
            )
            st.divider()
            st.caption("최근 시스템 로그")
            for l in st.session_state.log[-4:]: st.write(f"· {l}")
    else:
        st.error("🚨 인력 부족! 사이드바에서 출근 상태를 확인하십시오.")

st.title("🛡️ YULfactory: 지능형 공정 보건 관제 시스템")
update_dashboard()

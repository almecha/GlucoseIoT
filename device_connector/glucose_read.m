clc
close all 
clear 
data = readtable('glucose_data_simulated_extreme.csv');

% Extraer columnas
timestamps = datetime(data.timestamp, 'InputFormat','yyyy-MM-dd''T''HH:mm:ss');
glucose = data.glucose;

figure;
plot(timestamps, glucose, 'b-','LineWidth',1.5);
xlabel('Time');
ylabel('Glucose (mg/dL)');
title('Glucose levels simulation');
grid on;
hold on;
yline(70, 'r--', 'Hipoglucemia (<70)', 'LabelHorizontalAlignment','left');
yline(180, 'm--', 'Hiperglucemia (>180)', 'LabelHorizontalAlignment','left');

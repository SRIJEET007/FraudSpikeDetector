package com.example.fraudDetector.model;

import lombok.Data;

@Data
public class cardBaseLine {
    private double ewmaMean = 0.0;
    private double ewmaVar = 1.0;
    private boolean isInitialized = false;

    private static final double ALPHA = 0.2;

    public void update(double currentValue, boolean isSuspicious)
    {
        double valueToLearn = currentValue;
        if(!isInitialized)
        {
            ewmaMean = currentValue;
            ewmaVar = 1.0;
            isInitialized = true;
            return;
        }
        //protection against continuous fraud spikes - so that the baseline is not affected.
        if(isSuspicious)
        {
            valueToLearn = ewmaMean + 3 * getStandardDeviation();
        }
        double error = valueToLearn - ewmaMean;
        ewmaMean += (ALPHA*error);
        double squaredErr = error*error;
        ewmaVar = (1-ALPHA) * ewmaVar + (ALPHA*squaredErr);
    }

    public double getStandardDeviation()
    {
        return Math.sqrt(Math.max(ewmaVar,0.1));
    }
}

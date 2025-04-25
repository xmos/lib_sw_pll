// This file relates to internal XMOS infrastructure and should be ignored by external users

@Library('xmos_jenkins_shared_library@v0.38.0') _

getApproval()

pipeline {
    agent none

    environment {
        REPO = 'lib_sw_pll'
        PYTHON_VERSION = "3.12.1"
    }
    options {
        buildDiscarder(xmosDiscardBuildSettings())
        skipDefaultCheckout()
        timestamps()
    }
    parameters {
        string(
            name: 'TOOLS_VERSION',
            defaultValue: '15.3.1',
            description: 'The XTC tools version'
        )
        string(
            name: 'XMOSDOC_VERSION',
            defaultValue: 'v7.0.0',
            description: 'The xmosdoc version'
        )
        string(
            name: 'INFR_APPS_VERSION',
            defaultValue: 'v2.0.1',
            description: 'The infr_apps version'
        )
    }

    stages {
        stage('Build and tests') {
            agent {
                label 'linux&&64'
            }
            stages{
                stage('Build examples'){
                    steps {
                        dir("${REPO}") {
                            checkout scm
                            withTools(params.TOOLS_VERSION) {
                                dir("examples") {
                                    sh 'cmake -B build -G "Unix Makefiles"'
                                    sh 'xmake -j 16 -C build'
                                }
                            }
                        }
                    }
                }

                stage('Library checks') {
                    steps {
                        runLibraryChecks("${WORKSPACE}/${REPO}", "${params.INFR_APPS_VERSION}")
                    }
                }

                stage('Documentation') {
                    steps {
                        dir("${REPO}") {
                            warnError("Docs") {
                                buildDocs()
                            }
                        }
                    }
                }

                stage('Test'){
                    steps {
                        dir("${REPO}/tests") {
                            createVenv(reqFile: "requirements.txt")
                            withTools(params.TOOLS_VERSION) {
                                sh 'cmake -B build -G "Unix Makefiles"'
                                sh 'xmake -j 16 -C build'
                                withVenv {
                                    sh 'pytest --junitxml=results.xml -rA -v --durations=0 -o junit_logging=all'
                                    junit 'results.xml'
                                }
                                zip archive: true, zipFile: "tests.zip", dir: "bin"
                                archiveArtifacts artifacts: "bin/timing-report*.txt", allowEmptyArchive: false
                            }
                        }
                    }
                }

                stage('Python examples'){
                    steps {
                        dir("${REPO}/python") {
                            createVenv(reqFile: "requirements.txt")
                            withVenv {
                                dir("sw_pll") {
                                    sh 'python sw_pll_sim.py LUT'
                                    sh 'python sw_pll_sim.py SDM'
                                }
                            }
                            archiveArtifacts artifacts: "sw_pll/*.png,python/sw_pll/*.wav", allowEmptyArchive: false
                        }
                    }
                }
                stage("Archive sandbox") {
                    steps
                    {
                        archiveSandbox(REPO)
                    }
                }
            }
            post {
                cleanup {
                    xcoreCleanSandbox()
                }
            }
        }
    }
}

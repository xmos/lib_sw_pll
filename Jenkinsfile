@Library('xmos_jenkins_shared_library@v0.23.0') _


getApproval()


pipeline {
    agent none

    options {
        disableConcurrentBuilds()
        skipDefaultCheckout()
        timestamps()
        // on develop discard builds after a certain number else keep forever
        buildDiscarder(logRotator(
            numToKeepStr:         env.BRANCH_NAME ==~ /develop/ ? '25' : '',
            artifactNumToKeepStr: env.BRANCH_NAME ==~ /develop/ ? '25' : ''
        ))
    }
    parameters {
        string(
            name: 'TOOLS_VERSION',
            defaultValue: '15.1.4',
            description: 'The XTC tools version'
        )
    }
    environment {
        PYTHON_VERSION = "3.10.5"
        VENV_DIRNAME = ".venv"
    }

    stages {
        stage('ci') {
            agent {
                label 'linux&&64'
            }
            steps {
                sh 'mkdir lib_sw_pll'
                // source checks require the directory
                // name to be the same as the repo name
                dir('lib_sw_pll') {
                    // checkout repo
                    checkout scm
                    installPipfile(false)
                    withVenv {
                        withTools(params.TOOLS_VERSION) {
                            sh './tools/ci/checkout-submodules.sh'
                            catchError {
                                sh './tools/ci/do-ci.sh'
                            }
                            zip archive: true, zipFile: "build.zip", dir: "build"
                            zip archive: true, zipFile: "tests.zip", dir: "tests/bin"
                            archiveArtifacts artifacts: "tests/bin/timing-report.txt", allowEmptyArchive: false

                            junit 'tests/results.xml'
                        }
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
